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

    def ask(self, prompt: str, *, system: str = "", context: str = "") -> Reply:
        return Reply(error=f"a {self.target.kind} target is not asked questions")

    def tools(self) -> list:
        return []

    def call_tool(self, name: str, arguments: dict) -> Reply:
        return Reply(error=f"a {self.target.kind} target has no tools")

    def close(self) -> None:
        pass


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
                    raw = e.read(4096)
                except (OSError, http.client.HTTPException):
                    raw = b""
            return Reply(status=e.code, error=f"HTTP {e.code}", text=raw.decode("utf-8", "replace"), raw=raw[:4096].decode("utf-8", "replace"), latency_ms=ms)
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            return Reply(error=f"unreachable: {type(reason).__name__}: {reason}"[:300], latency_ms=int((time.monotonic() - start) * 1000))
        except (ValueError, http.client.HTTPException) as e:
            return send_failed(e, int((time.monotonic() - start) * 1000))
        ms = int((time.monotonic() - start) * 1000)
        if len(raw) > t.max_response_bytes:
            return Reply(status=status, error=f"the response is larger than {t.max_response_bytes} bytes", latency_ms=ms)
        text = raw.decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except ValueError:
            return Reply(status=status, text=text, raw=text[:4096], latency_ms=ms)
        r = t.response
        usage = {k: pick(data, r[k]) for k in ("usage_in", "usage_out") if r.get(k) and pick(data, r[k]) is not None}
        return Reply(status=status, text=as_text(pick(data, r.get("text", ""))), tool_calls=normalise_tool_calls(pick(data, r.get("tool_calls", ""))),
                     citations=pick(data, r.get("citations", "")) or [], latency_ms=ms, usage=usage, raw=text[:4096])


class CommandAdapter(Adapter):
    """One process per question: a JSON line on stdin ({prompt, system, context}), the answer on stdout (JSON with
    `output` or `text`, or plain text)."""

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
        out = p.stdout[: t.max_response_bytes].decode("utf-8", "replace").strip()
        if p.returncode != 0:
            return Reply(status=p.returncode, error=f"exit {p.returncode}: {p.stderr.decode('utf-8', 'replace').strip()[-300:]}", text=out, latency_ms=ms)
        data = answer_line(out)
        if data is None:
            try:
                data = json.loads(out)
            except ValueError:
                return Reply(status=0, text=out, raw=out[:4096], latency_ms=ms)
        if not isinstance(data, dict):
            return Reply(status=0, text=as_text(data), raw=out[:4096], latency_ms=ms)
        return Reply(status=0, text=as_text(data.get("output", data.get("text"))), tool_calls=normalise_tool_calls(data.get("tool_calls")),
                     citations=data.get("citations") or [], raw=out[:4096], latency_ms=ms)

    def cwd(self):
        return None


def answer_line(out: str):
    """The answer when the last non-empty line of the output is a JSON object: whatever the solution (or a child
    process of it) printed before that is noise, not the answer. None otherwise."""
    lines = [line for line in out.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    try:
        data = json.loads(lines[-1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


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


def tool_reply(msg: dict, ms: int) -> Reply:
    if "error" in msg:
        err = msg["error"] if isinstance(msg["error"], dict) else {"message": str(msg["error"])}
        return Reply(status=err.get("code"), error=f"JSON-RPC {err.get('code')}: {str(err.get('message'))[:300]}", raw=json.dumps(msg)[:4096], latency_ms=ms)
    result = msg.get("result") or {}
    text = as_text(result.get("content")) if isinstance(result, dict) else as_text(result)
    r = Reply(status=0, text=text, raw=json.dumps(msg)[:4096], latency_ms=ms, result=result)
    if isinstance(result, dict) and result.get("isError"):
        r.error = "tool error: " + text[:300]
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
        lines = [line.strip() for line in bytes(self.stderr_tail).decode("utf-8", "replace").splitlines() if line.strip()]
        return lines[-1][-200:] if lines else ""

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
                return tool_reply(answer, ms)

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
                    text = e.read(2048).decode("utf-8", "replace")
                except (OSError, http.client.HTTPException):
                    text = ""
            return Reply(status=e.code, error=f"HTTP {e.code}", text=text, latency_ms=ms)
        except (urllib.error.URLError, OSError) as e:
            return Reply(error=f"unreachable: {getattr(e, 'reason', e)}"[:300])
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
                return tool_reply(answer, ms)
        return Reply(error="no JSON-RPC answer to the call", raw=raw[:4096], latency_ms=ms)

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
                     latency_ms=int((time.monotonic() - start) * 1000) + 1, raw=json.dumps(out)[:4096])


def open_target(target: C.Target) -> Adapter:
    return {"http": HttpAdapter, "command": CommandAdapter, "python": PythonAdapter, "mcp-stdio": McpStdioAdapter,
            "mcp-http": McpHttpAdapter, "demo": DemoAdapter}[target.kind](target)
