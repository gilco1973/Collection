"""Adapters: one way to reach each kind of solution, all answering with a Reply.

A chat-shaped solution (an assistant, an agent behind an API, a model gateway, a Python function, a command) is
asked with `ask`; a tool server (MCP over stdio or HTTP) is listed with `tools` and called with `call_tool`. Every
adapter enforces the target's timeout and response cap and turns every failure into a Reply with `error` set, so a
probe run never stops on one bad answer.
"""
from __future__ import annotations

import http.client
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from . import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
MCP_PROTOCOL = "2025-06-18"


@dataclass
class Reply:
    text: str = ""
    tool_calls: list = field(default_factory=list)    # [{"name": str, "arguments": dict}]
    citations: list = field(default_factory=list)
    status: int | None = None                        # HTTP status, process exit code, or a JSON-RPC error code
    error: str | None = None
    latency_ms: int = 0
    usage: dict = field(default_factory=dict)
    raw: str = ""                                    # the response as received, cut to 4 KB
    result: object = field(default=None, repr=False, compare=False)   # MCP: the parsed JSON-RPC result, whole; not in to_json

    def ok(self) -> bool:
        return self.error is None

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in ("text", "tool_calls", "citations", "status", "error", "latency_ms", "usage", "raw")}


# --- helpers -----------------------------------------------------------------------------------------------------

def fill(template, values: dict):
    """Substitute {{name}} placeholders inside a JSON template. A string that is exactly one placeholder takes the
    value with its type (a list of messages stays a list); a placeholder inside a longer string is text."""
    if isinstance(template, str):
        m = re.fullmatch(r"\{\{(\w+)\}\}", template)
        if m and m.group(1) in values:
            return values[m.group(1)]
        return re.sub(r"\{\{(\w+)\}\}", lambda mm: str(values.get(mm.group(1), "")) if not isinstance(values.get(mm.group(1)), (list, dict)) else json.dumps(values[mm.group(1)]), template)
    if isinstance(template, list):
        return [fill(v, values) for v in template]
    if isinstance(template, dict):
        return {k: fill(v, values) for k, v in template.items()}
    return template


def pick(data, path: str):
    """A value by a dotted path: `choices.0.message.content`; a segment `name[key=value]` keeps the list items whose
    key equals value. Missing anything is None."""
    if not path:
        return None
    cur = data
    for seg in path.split("."):
        m = re.fullmatch(r"([^\[]*)\[(\w+)=([^\]]*)\]", seg)
        name = m.group(1) if m else seg
        if name:
            if isinstance(cur, list) and name.isdigit():
                i = int(name)
                cur = cur[i] if i < len(cur) else None
            elif isinstance(cur, dict):
                cur = cur.get(name)
            else:
                return None
        if m:
            if not isinstance(cur, list):
                return None
            cur = [x for x in cur if isinstance(x, dict) and str(x.get(m.group(2))) == m.group(3)]
        if cur is None:
            return None
    return cur


def normalise_tool_calls(calls) -> list:
    out = []
    for c in calls or []:
        if not isinstance(c, dict):
            continue
        fn = c.get("function") if isinstance(c.get("function"), dict) else c
        args = fn.get("arguments", fn.get("input", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"_raw": args}
        out.append({"name": str(fn.get("name", "")), "arguments": args if isinstance(args, dict) else {"_value": args}})
    return out


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):   # a list of content blocks; a block's text may be anything a solution sends
        parts = (v.get("text") if isinstance(v, dict) else v for v in value)
        return "".join(p if isinstance(p, str) else json.dumps(p, default=str) if isinstance(p, (list, dict)) else str(p)
                       for p in parts if p is not None)
    return json.dumps(value, default=str)


def child_env(names) -> dict:
    """What a spawned solution sees: a minimal environment plus the variables the target names."""
    keep = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP") if k in os.environ}
    keep.update({n: os.environ[n] for n in names if n in os.environ})
    keep["PYTHONDONTWRITEBYTECODE"] = "1"
    return keep


SECRET_MARK = "[secret]"
MIN_FRAGMENT = 8   # the shortest piece of a credential scrubbed where text was cut; shorter pieces are ordinary text


def scrub_text(text: str, secrets) -> str:
    """The text with every credential value replaced by [secret], longest first (a value inside another is not left
    half-shown), and, defensively, a piece of a credential of at least MIN_FRAGMENT characters that sits at an edge
    of the text: the text starts with the end of a value, or ends with its start, where something cut it."""
    if not text or not secrets:
        return text
    values = sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True)
    for s in values:
        text = text.replace(s, SECRET_MARK)
    for s in values:
        for n in range(len(s) - 1, MIN_FRAGMENT - 1, -1):     # the longest piece first
            if text.startswith(s[-n:]):
                text = SECRET_MARK + text[n:]
                break
        for n in range(len(s) - 1, MIN_FRAGMENT - 1, -1):
            if text.endswith(s[:n]):
                text = text[:-n] + SECRET_MARK
                break
    return text


def clip(text: str, limit: int, secrets, *, tail: bool = False) -> str:
    """At most `limit` characters of the text (its start, or its end with `tail`), scrubbed BEFORE the cut, so a cut
    never leaves part of a credential that no longer matches the whole value."""
    text = scrub_text(text or "", secrets)
    if len(text) > limit:
        text = scrub_text(text[-limit:] if tail else text[:limit], secrets)
    return text


def clip_bytes(data: bytes, limit: int, secrets, *, tail: bool = False) -> str:
    """At most `limit` bytes of output (its start, or its end with `tail`) as text, scrubbed before the cut: a margin
    as long as the longest credential is read past the limit, so a value that straddles it is still whole."""
    margin = max((len(s.encode("utf-8")) for s in secrets or () if isinstance(s, str)), default=0)
    part = data[-(limit + margin):] if tail else data[: limit + margin]
    text = scrub_text(part.decode("utf-8", "replace"), secrets)
    enc = text.encode("utf-8")
    if len(enc) > limit:
        text = scrub_text((enc[-limit:] if tail else enc[:limit]).decode("utf-8", "ignore"), secrets)
    return text


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: following one would send the request (and its Authorization header) to a host that
    was never checked against `allow_hosts`, and judge that host's answer as the solution's."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None   # the 3xx then surfaces as an HTTPError


_OPENER = urllib.request.build_opener(_NoRedirect)


def redirect_reply(e: urllib.error.HTTPError, url: str, ms: int) -> Reply:
    location = e.headers.get("Location", "") if e.headers else ""
    host = urllib.parse.urlsplit(urllib.parse.urljoin(url, location)).hostname if location else None
    return Reply(status=e.code, error=f"redirected to {host or 'an unnamed location'}: the playground does not follow redirects", latency_ms=ms)


def send_failed(e: Exception, ms: int) -> Reply:
    """A request that could not be sent or read. Never str(e) for a ValueError: http.client puts the offending header
    value, a credential, in the message."""
    if isinstance(e, ValueError):
        return Reply(error="the request could not be sent: a header or the address is not valid", latency_ms=ms)
    return Reply(error=f"the request failed: {type(e).__name__}", latency_ms=ms)


# --- adapters ----------------------------------------------------------------------------------------------------

class Adapter:
    chat = True
    tool_server = False

    def __init__(self, target: C.Target):
        self.target = target
        # The values behind the target's credential names, read once: every error, text and raw an adapter returns is
        # scrubbed of them before it is cut, so no cut leaves part of a value behind (the report scrubs whole values).
        self.secrets = C.secret_values(target)

    def ask(self, prompt: str, *, system: str = "", context: str = "") -> Reply:
        return Reply(error=f"a {self.target.kind} target is not asked questions")

    def tools(self) -> list:
        return []

    def call_tool(self, name: str, arguments: dict) -> Reply:
        return Reply(error=f"a {self.target.kind} target has no tools")

    def close(self) -> None:
        pass

    def _margin(self) -> int:
        """How far past a byte limit to read so a credential that straddles it is still whole when it is scrubbed."""
        return max((len(s.encode("utf-8")) for s in self.secrets), default=0)


class HttpAdapter(Adapter):
    def ask(self, prompt, *, system="", context=""):
        t = self.target
        sys_text = "\n\n".join(s for s in (t.system, system) if s)
        user = f"{context}\n\n{prompt}" if context and "{{context}}" not in json.dumps(t.body) else prompt
        messages = ([{"role": "system", "content": sys_text}] if sys_text else []) + [{"role": "user", "content": user}]
        values = {"prompt": user if "{{context}}" not in json.dumps(t.body) else prompt, "system": sys_text, "context": context,
                  "messages": messages, "messages_no_system": [m for m in messages if m["role"] != "system"], "model": t.model}
        try:
            # Secrets are resolved in the target's own template first, then the prompt's text is filled in: text from
            # a prompt, a context or a system message is sent as written, never read as `${env:...}`.
            body = fill(C.resolve_secrets(t.body), values)
            headers = C.resolve_secrets(dict(t.headers))
        except C.ConfigError as e:
            return Reply(error=str(e))
        return self._send(json.dumps(body).encode("utf-8"), headers)

    def _send(self, data: bytes, headers: dict) -> Reply:
        t = self.target
        start = time.monotonic()
        try:
            req = urllib.request.Request(t.url, data=data, method=t.method, headers=headers)
            with _OPENER.open(req, timeout=t.timeout_s) as resp:
                raw = resp.read(t.max_response_bytes + 1)
                status = resp.status
        except urllib.error.HTTPError as e:
            ms = int((time.monotonic() - start) * 1000)
            with e:
                if 300 <= e.code < 400:
                    return redirect_reply(e, t.url, ms)
                try:
                    raw = e.read(4096 + self._margin())
                except (OSError, http.client.HTTPException):
                    raw = b""
            body = clip_bytes(raw, 4096, self.secrets)
            return Reply(status=e.code, error=f"HTTP {e.code}", text=body, raw=body, latency_ms=ms)
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            return Reply(error=clip(f"unreachable: {type(reason).__name__}: {reason}", 300, self.secrets), latency_ms=int((time.monotonic() - start) * 1000))
        except (ValueError, http.client.HTTPException) as e:
            return send_failed(e, int((time.monotonic() - start) * 1000))
        ms = int((time.monotonic() - start) * 1000)
        if len(raw) > t.max_response_bytes:
            return Reply(status=status, error=f"the response is larger than {t.max_response_bytes} bytes", latency_ms=ms)
        text = raw.decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except ValueError:
            return Reply(status=status, text=scrub_text(text, self.secrets), raw=clip(text, 4096, self.secrets), latency_ms=ms)
        r = t.response
        usage = {k: pick(data, r[k]) for k in ("usage_in", "usage_out") if r.get(k) and pick(data, r[k]) is not None}
        return Reply(status=status, text=scrub_text(as_text(pick(data, r.get("text", ""))), self.secrets),
                     tool_calls=normalise_tool_calls(pick(data, r.get("tool_calls", ""))),
                     citations=pick(data, r.get("citations", "")) or [], latency_ms=ms, usage=usage, raw=clip(text, 4096, self.secrets))


class CommandAdapter(Adapter):
    """One process per question: a JSON line on stdin ({prompt, system, context}), the answer on stdout: a JSON object
    with `output` or `text` (the last such line wins; log lines around it are ignored), or plain text (then the
    lines of stdout that are not JSON are the answer, and a line carrying only `tool_calls`, a trace of the step,
    adds its tool calls). See command_answer."""

    def argv(self) -> list:
        return list(self.target.command)

    def ask(self, prompt, *, system="", context=""):
        t = self.target
        line = json.dumps({"prompt": prompt, "system": "\n\n".join(s for s in (t.system, system) if s), "context": context}) + "\n"
        start = time.monotonic()
        try:
            p = subprocess.run(self.argv(), input=line.encode("utf-8"), capture_output=True, timeout=t.timeout_s, env=child_env(t.env), cwd=self.cwd())
        except subprocess.TimeoutExpired:
            return Reply(error=f"no answer within {t.timeout_s} s", latency_ms=int(t.timeout_s * 1000))
        except OSError as e:
            return Reply(error=f"cannot start the command: {e.strerror}")
        ms = int((time.monotonic() - start) * 1000)
        # scrubbed before anything is cut: the response cap here, 300 characters of stderr, 4 KB of raw
        out = clip_bytes(p.stdout, int(t.max_response_bytes), self.secrets).strip()
        if p.returncode != 0:
            err = scrub_text(p.stderr.decode("utf-8", "replace"), self.secrets).strip()
            return Reply(status=p.returncode, error=f"exit {p.returncode}: {clip(err, 300, self.secrets, tail=True)}", text=out, latency_ms=ms)
        raw = clip(out, 4096, self.secrets)
        ans = command_answer(out)
        return Reply(status=0, text=ans["text"], tool_calls=ans["tool_calls"], citations=ans["citations"], raw=raw, latency_ms=ms)

    def cwd(self):
        return None


ANSWER_KEYS = ("output", "text")        # an object carrying one of these is the answer
TOOL_KEY = "tool_calls"                 # an object carrying only this (a step's trace) adds its tool calls


def _answer_text(data: dict) -> str:
    return as_text(data["output"] if data.get("output") is not None else data.get("text"))


def _unique_calls(calls: list) -> list:
    seen, out = set(), []
    for c in calls:
        key = json.dumps(c, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def command_answer(out: str) -> dict:
    """{text, tool_calls, citations} from a command's stdout.

    - The whole output is one JSON value: an object with `output`, `text` or `tool_calls` is read as such; a string,
      number or list is the text; anything else (an object without those keys) leaves the whole output as the text.
    - Otherwise, line by line: the answer object is the LAST line that parses to a JSON object carrying `output` or
      `text`; lines before and after it (progress, a structured log record `{"level": "info", ...}`) are never the
      answer. A line carrying `tool_calls` but no text (a trace of the step, `{"step": "final", "tool_calls": []}`)
      is not the answer either: it adds its tool calls. The text is the answer object's; when there is none, or it
      is empty, the text is the lines of stdout that are not JSON objects or lists, so a plain-text answer followed
      by a trace line is still read (and a marker in it still found). With neither an answer object nor a trace
      line, the whole output is the text."""
    empty = {"text": "", "tool_calls": [], "citations": []}
    try:
        whole = json.loads(out)
    except ValueError:
        whole = ValueError
    if whole is not ValueError:
        if isinstance(whole, dict):
            if any(k in whole for k in ANSWER_KEYS + (TOOL_KEY,)):
                return {"text": _answer_text(whole), "tool_calls": normalise_tool_calls(whole.get(TOOL_KEY)),
                        "citations": whole.get("citations") or []}
            return dict(empty, text=out)
        if isinstance(whole, (str, int, float, list)) and not isinstance(whole, bool):
            return dict(empty, text=as_text(whole))
        return dict(empty, text=out)
    lines = out.splitlines()
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line) if line.strip() else None)
        except ValueError:
            parsed.append(None)
    answer = next((d for d in reversed(parsed) if isinstance(d, dict) and any(k in d for k in ANSWER_KEYS)), None)
    traces = [d for d in parsed if isinstance(d, dict) and TOOL_KEY in d and not any(k in d for k in ANSWER_KEYS)]
    if answer is None and not traces:
        return dict(empty, text=out)   # no answer object anywhere: the whole output is the text
    plain = "\n".join(line for line, d in zip(lines, parsed) if not isinstance(d, (dict, list))).strip()
    calls = []
    for d in traces + ([answer] if answer is not None else []):
        calls += normalise_tool_calls(d.get(TOOL_KEY))
    text = _answer_text(answer) if answer is not None else ""
    citations = (answer or {}).get("citations") or next((d.get("citations") for d in reversed(traces) if d.get("citations")), None) or []
    return {"text": text if text.strip() else plain, "tool_calls": _unique_calls(calls), "citations": citations}


class PythonAdapter(CommandAdapter):
    """A function in the solution's own directory, called in a fresh interpreter per question through shim.py, so
    the solution's imports, globals and crashes stay out of the playground's process."""

    def argv(self):
        return [sys.executable, os.path.join(HERE, "shim.py"), self.target.path, self.target.callable]

    def cwd(self):
        return self.target.path


class _Rpc:
    """JSON-RPC ids and the answers to requests a server sends back (elicitation is declined)."""

    def __init__(self):
        self.next_id = 0

    def request(self, method, params=None):
        self.next_id += 1
        return {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}


def tool_reply(msg: dict, ms: int, secrets=()) -> Reply:
    """A JSON-RPC answer as a Reply; error, text and raw are scrubbed of `secrets` before they are cut."""
    if "error" in msg:
        err = msg["error"] if isinstance(msg["error"], dict) else {"message": str(msg["error"])}
        return Reply(status=err.get("code"), error=f"JSON-RPC {err.get('code')}: {clip(str(err.get('message')), 300, secrets)}",
                     raw=clip(json.dumps(msg), 4096, secrets), latency_ms=ms)
    result = msg.get("result") or {}
    text = scrub_text(as_text(result.get("content")) if isinstance(result, dict) else as_text(result), secrets)
    r = Reply(status=0, text=text, raw=clip(json.dumps(msg), 4096, secrets), latency_ms=ms, result=result)
    if isinstance(result, dict) and result.get("isError"):
        r.error = "tool error: " + clip(text, 300, secrets)
    return r


def listed_tools(r: Reply) -> list:
    """The tools of a tools/list answer, from the parsed result (Reply.raw is cut to 4 KB)."""
    if r.error:
        raise RuntimeError(f"tools/list failed: {r.error}")
    tools = r.result.get("tools") if isinstance(r.result, dict) else None
    return [t for t in tools if isinstance(t, dict)] if isinstance(tools, list) else []


class _Oversized:
    """Queued by the reader in place of a line longer than the response cap (the line itself is discarded)."""


STDERR_KEEP = 2048


class McpStdioAdapter(Adapter):
    chat = False
    tool_server = True

    def __init__(self, target):
        super().__init__(target)
        self.rpc = _Rpc()
        self.lines: queue.Queue = queue.Queue()
        self.proc = None
        self.started = False
        self.restarts = 0            # how often the server died during the run and was started again
        self.stderr_tail = bytearray()
        self.stderr_reader = None

    def _start(self):
        if self.started and self.proc is not None and self.proc.poll() is not None:
            self.restarts += 1       # it died: start a fresh one so the rest of the run still judges something
            self._release(self.proc)
            self.started = False
            self.lines = queue.Queue()
        if self.started:
            return
        self.started = True
        self.stderr_tail = bytearray()
        self.proc = subprocess.Popen(self.target.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env(self.target.env))
        threading.Thread(target=self._read, args=(self.proc.stdout, self.lines, int(self.target.max_response_bytes)), daemon=True).start()
        self.stderr_reader = threading.Thread(target=self._read_stderr, args=(self.proc.stderr, self.stderr_tail), daemon=True)
        self.stderr_reader.start()
        init = self._call("initialize", {"protocolVersion": MCP_PROTOCOL, "capabilities": {}, "clientInfo": {"name": "ai-playground", "version": "1"}})
        if init.error:
            raise RuntimeError(f"initialize failed: {init.error}")
        try:
            self._write({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, time.monotonic() + self.target.timeout_s)
        except (TimeoutError, OSError):
            pass   # the next call finds the server dead or stuck and says so

    @staticmethod
    def _read(pipe, lines, cap):
        """Lines of the server's stdout, each read with a bound: a line longer than `cap` bytes is discarded as it
        arrives and queued as _Oversized, so a flood never sits in memory. The reader owns the pipe and closes it."""
        try:
            while True:
                line = pipe.readline(cap + 1)
                if not line:
                    break
                if len(line) > cap and not line.endswith(b"\n"):
                    while True:   # skip the rest of the line
                        rest = pipe.readline(65536)
                        if not rest or rest.endswith(b"\n"):
                            break
                    lines.put(_Oversized())
                    continue
                lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)
            try:
                pipe.close()
            except (OSError, ValueError):
                pass

    @staticmethod
    def _read_stderr(pipe, tail):
        """Keeps the last STDERR_KEEP bytes of the server's stderr: why it exited, when it does."""
        try:
            while True:
                chunk = pipe.read1(4096)
                if not chunk:
                    break
                tail.extend(chunk)
                del tail[:-STDERR_KEEP]
        except (OSError, ValueError):
            pass
        finally:
            try:
                pipe.close()
            except (OSError, ValueError):
                pass

    def _stderr_line(self) -> str:
        if self.stderr_reader is not None:
            self.stderr_reader.join(0.5)   # the server has exited: let the last of its stderr arrive
        # the kept tail starts wherever the last STDERR_KEEP bytes began: scrubbed (edges too) before the line is cut
        tail = scrub_text(bytes(self.stderr_tail).decode("utf-8", "replace"), self.secrets)
        lines = [line.strip() for line in tail.splitlines() if line.strip()]
        return clip(lines[-1], 200, self.secrets, tail=True) if lines else ""

    def _exited(self, ms: int = 0) -> Reply:
        last = self._stderr_line()
        return Reply(error="the server has exited" + (f" (its last words on stderr: {last})" if last else ""), latency_ms=ms)

    def _write(self, msg, deadline):
        """Sends one message, bounded by the deadline. A server that stops reading would block a plain write for good,
        so the write runs in a thread; when it is still stuck at the deadline the server is killed (the next call
        starts a fresh one, counted in `restarts`) and TimeoutError is raised."""
        proc, data, failed = self.proc, (json.dumps(msg) + "\n").encode("utf-8"), []

        def write():
            try:
                proc.stdin.write(data)
                proc.stdin.flush()
            except (OSError, ValueError) as e:
                failed.append(e)

        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        writer.join(max(0.0, deadline - time.monotonic()))
        if writer.is_alive():
            self._kill(proc)
            writer.join(3)
            raise TimeoutError
        if failed:
            raise BrokenPipeError

    @staticmethod
    def _kill(proc):
        try:
            proc.kill()
            proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _call(self, method, params) -> Reply:
        msg = self.rpc.request(method, params)
        start = time.monotonic()
        deadline = start + self.target.timeout_s
        timed_out = Reply(error=f"no answer within {self.target.timeout_s} s", latency_ms=int(self.target.timeout_s * 1000))
        try:
            self._write(msg, deadline)
        except TimeoutError:
            return timed_out
        except OSError:
            return self._exited()
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return timed_out
            try:
                line = self.lines.get(timeout=left)
            except queue.Empty:
                continue
            ms = int((time.monotonic() - start) * 1000)
            if line is None:
                return self._exited(ms)
            if isinstance(line, _Oversized):
                return Reply(error=f"the answer is larger than {self.target.max_response_bytes} bytes", latency_ms=ms)
            try:
                answer = json.loads(line)
            except ValueError:
                continue   # a server that logs to stdout; not ours to answer
            if isinstance(answer, dict) and answer.get("method") and "id" in answer:   # a request from the server
                try:
                    self._write({"jsonrpc": "2.0", "id": answer["id"], "error": {"code": -32601, "message": "the playground declines server requests"}}, deadline)
                except TimeoutError:
                    return timed_out
                except OSError:
                    return self._exited(ms)
                continue
            if isinstance(answer, dict) and answer.get("id") == msg["id"]:
                return tool_reply(answer, ms, self.secrets)

    def raw(self, method: str, params) -> Reply:
        """Any method, with any params: the tool probes send malformed calls on purpose."""
        try:
            self._start()
        except (RuntimeError, OSError) as e:
            return Reply(error=str(e))
        return self._call(method, params)

    def tools(self):
        return listed_tools(self.raw("tools/list", {}))

    def call_tool(self, name, arguments):
        return self.raw("tools/call", {"name": name, "arguments": arguments})

    @staticmethod
    def _release(proc):
        # stdout and stderr belong to their reader threads, which close them at end of file
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass

    def close(self):
        if not self.proc:
            return
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=3)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait(timeout=3)
        self._release(self.proc)


class McpHttpAdapter(Adapter):
    chat = False
    tool_server = True

    def __init__(self, target):
        super().__init__(target)
        self.rpc = _Rpc()
        self.session = None
        self.started = False

    def _post(self, msg) -> Reply:
        t = self.target
        try:
            # only the target's own header templates are resolved; nothing from a call's arguments is
            headers = C.resolve_secrets({"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **t.headers})
        except C.ConfigError as e:
            return Reply(error=str(e))
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        start = time.monotonic()
        try:
            req = urllib.request.Request(t.url, data=json.dumps(msg).encode("utf-8"), method="POST", headers=headers)
            with _OPENER.open(req, timeout=t.timeout_s) as resp:
                self.session = resp.headers.get("Mcp-Session-Id") or self.session
                body = resp.read(t.max_response_bytes + 1)
                status = resp.status
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            ms = int((time.monotonic() - start) * 1000)
            with e:
                if 300 <= e.code < 400:
                    return redirect_reply(e, t.url, ms)
                try:
                    text = clip_bytes(e.read(2048 + self._margin()), 2048, self.secrets)
                except (OSError, http.client.HTTPException):
                    text = ""
            return Reply(status=e.code, error=f"HTTP {e.code}", text=text, latency_ms=ms)
        except (urllib.error.URLError, OSError) as e:
            return Reply(error=clip(f"unreachable: {getattr(e, 'reason', e)}", 300, self.secrets))
        except (ValueError, http.client.HTTPException) as e:
            return send_failed(e, int((time.monotonic() - start) * 1000))
        ms = int((time.monotonic() - start) * 1000)
        if len(body) > t.max_response_bytes:
            return Reply(status=status, error=f"the answer is larger than {t.max_response_bytes} bytes", latency_ms=ms)
        raw = body.decode("utf-8", "replace")
        if "id" not in msg:
            return Reply(status=202, latency_ms=ms)
        bodies = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")] if "event-stream" in ctype else [raw]
        for b in bodies:
            try:
                answer = json.loads(b)
            except ValueError:
                continue
            if isinstance(answer, dict) and answer.get("id") == msg["id"]:
                return tool_reply(answer, ms, self.secrets)
        return Reply(error="no JSON-RPC answer to the call", raw=clip(raw, 4096, self.secrets), latency_ms=ms)

    def raw(self, method, params):
        if not self.started:
            self.started = True
            init = self._post(self.rpc.request("initialize", {"protocolVersion": MCP_PROTOCOL, "capabilities": {}, "clientInfo": {"name": "ai-playground", "version": "1"}}))
            if init.error:
                self.started = False
                return init
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return self._post(self.rpc.request(method, params))

    def tools(self):
        return listed_tools(self.raw("tools/list", {}))

    def call_tool(self, name, arguments):
        return self.raw("tools/call", {"name": name, "arguments": arguments})


class DemoAdapter(Adapter):
    """The bundled demo assistants, in process: `safe` holds every line the probes test, `vulnerable` gives most up."""

    def __init__(self, target):
        super().__init__(target)
        from . import demo
        self.bot = demo.SafeAssistant() if target.demo == "safe" else demo.VulnerableAssistant()

    def ask(self, prompt, *, system="", context=""):
        start = time.monotonic()
        out = self.bot.answer(prompt, system="\n\n".join(s for s in (self.target.system, system) if s), context=context)
        return Reply(status=0, text=out.get("output", ""), tool_calls=normalise_tool_calls(out.get("tool_calls")), citations=out.get("citations") or [],
                     latency_ms=int((time.monotonic() - start) * 1000) + 1, raw=clip(json.dumps(out), 4096, self.secrets))


def open_target(target: C.Target) -> Adapter:
    return {"http": HttpAdapter, "command": CommandAdapter, "python": PythonAdapter, "mcp-stdio": McpStdioAdapter,
            "mcp-http": McpHttpAdapter, "demo": DemoAdapter}[target.kind](target)
