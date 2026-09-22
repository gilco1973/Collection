"""A target: the AI solution under test, described in one JSON file.

The file names how to reach the solution and nothing secret. A credential is written as `${env:NAME}` and read
from the environment at call time; reports and logs show the name, never the value. Two controls keep a probe run
from hurting anything: the target's `environment` must be a non-production one, and its host must be listed in
`allow_hosts` (loopback is always allowed). Both refusals are deliberate: probes are adversarial by design.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import dataclass, field

KINDS = ("http", "command", "python", "mcp-stdio", "mcp-http", "demo")
ENVIRONMENTS = ("sandbox", "dev", "test", "staging")
LOOPBACK = ("127.0.0.1", "localhost", "::1")
SECRET_REF = re.compile(r"\$\{env:([A-Z_][A-Z0-9_]*)\}")
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

# Request and response shapes of the common chat APIs, so a target file names a preset instead of a body.
PRESETS = {
    "openai-chat": {
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {"model": "{{model}}", "messages": "{{messages}}", "temperature": 0},
        "response": {"text": "choices.0.message.content", "tool_calls": "choices.0.message.tool_calls",
                     "usage_in": "usage.prompt_tokens", "usage_out": "usage.completion_tokens"},
    },
    "anthropic-messages": {
        "method": "POST",
        "headers": {"Content-Type": "application/json", "anthropic-version": "2023-06-01"},
        "body": {"model": "{{model}}", "max_tokens": 1024, "system": "{{system}}", "messages": "{{messages_no_system}}"},
        "response": {"text": "content.0.text", "tool_calls": "content[type=tool_use]",
                     "usage_in": "usage.input_tokens", "usage_out": "usage.output_tokens"},
    },
    "simple-json": {
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {"input": "{{prompt}}", "context": "{{context}}"},
        "response": {"text": "output", "citations": "citations", "tool_calls": "tool_calls"},
    },
}


class ConfigError(ValueError):
    """A target file that cannot be used; the message names the field."""


@dataclass
class Target:
    name: str
    kind: str
    environment: str
    description: str = ""
    owner: str = ""
    component: str = ""                       # the collection component this solution would become, if known
    url: str = ""
    preset: str = ""
    method: str = "POST"
    headers: dict = field(default_factory=dict)
    body: object = None
    response: dict = field(default_factory=dict)
    model: str = ""
    system: str = ""                          # the solution's own system prompt, when the tester supplies it
    command: list = field(default_factory=list)
    callable: str = ""                        # python: "module:function"
    path: str = ""                            # python: the directory the module is imported from
    env: list = field(default_factory=list)   # environment variable names passed to a command or python target
    allow_hosts: list = field(default_factory=list)
    timeout_s: float = 30.0
    max_response_bytes: int = 2_000_000
    concurrency: int = 4
    capabilities: list = field(default_factory=list)   # what the solution claims: masks-pii, cites-sources, refuses-money, ...
    demo: str = ""                            # demo: "safe" or "vulnerable"

    def secret_names(self) -> list:
        text = json.dumps([self.url, self.headers, self.body])
        return sorted(set(SECRET_REF.findall(text)))

    def describe(self) -> dict:
        """What a report shows about the target: its shape, never a credential value."""
        d = {"name": self.name, "kind": self.kind, "environment": self.environment, "description": self.description,
             "owner": self.owner, "component": self.component, "capabilities": self.capabilities}
        if self.kind in ("http", "mcp-http"):
            d.update(url=self.url, preset=self.preset or None, method=self.method,
                     headers={k: SECRET_REF.sub(lambda m: f"${{env:{m.group(1)}}}", str(v)) for k, v in self.headers.items()})
        if self.kind in ("command", "mcp-stdio"):
            d.update(command=self.command, env=self.env)
        if self.kind == "python":
            d.update(callable=self.callable, path=self.path, env=self.env)
        if self.kind == "demo":
            d.update(demo=self.demo)
        d["secrets"] = self.secret_names()
        return d


def resolve_secrets(value, env=None):
    """Replace every `${env:NAME}` in a string, list or dict; a missing variable is an error naming it."""
    env = os.environ if env is None else env
    if isinstance(value, str):
        def sub(m):
            if m.group(1) not in env:
                raise ConfigError(f"the environment variable {m.group(1)} is not set (the target reads a credential from it)")
            return env[m.group(1)]
        return SECRET_REF.sub(sub, value)
    if isinstance(value, list):
        return [resolve_secrets(v, env) for v in value]
    if isinstance(value, dict):
        return {k: resolve_secrets(v, env) for k, v in value.items()}
    return value


def secret_values(target: Target, env=None) -> list:
    """The values currently behind the target's secret names, so a report can scrub them from evidence."""
    env = os.environ if env is None else env
    return [env[n] for n in target.secret_names() + list(target.env) if env.get(n) and len(env[n]) >= 4]


def host_allowed(url: str, allow_hosts: list) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host in LOOPBACK:
        return True
    for pattern in allow_hosts:
        pattern = pattern.lower()
        if pattern.startswith("*.") and host.endswith(pattern[1:]) and host != pattern[2:]:
            return True
        if host == pattern:
            return True
    return False


def load(source) -> Target:
    """A target from a path or an already-parsed dict; every problem is one ConfigError naming the field."""
    if isinstance(source, (str, os.PathLike)):
        try:
            with open(source, encoding="utf-8") as f:
                raw = json.load(f)
        except OSError as e:
            raise ConfigError(f"cannot read the target file: {e.strerror}: {source}") from None
        except json.JSONDecodeError as e:
            raise ConfigError(f"the target file is not JSON: line {e.lineno}: {e.msg}") from None
        base = os.path.dirname(os.path.abspath(source))
    else:
        raw, base = dict(source), os.getcwd()
    if not isinstance(raw, dict):
        raise ConfigError("the target file must be one JSON object")
    known = set(Target.__dataclass_fields__)
    unknown = sorted(set(raw) - known - {"$comment"})
    if unknown:
        raise ConfigError(f"unknown field(s): {', '.join(unknown)}")
    raw.pop("$comment", None)
    for req in ("name", "kind", "environment"):
        if not raw.get(req):
            raise ConfigError(f"`{req}` is required")
    if not NAME.match(str(raw["name"])):
        raise ConfigError("`name` is lower case letters, digits, dot, dash or underscore, at most 64")
    if raw["kind"] not in KINDS:
        raise ConfigError(f"`kind` is one of {', '.join(KINDS)}")
    if raw["environment"] not in ENVIRONMENTS:
        raise ConfigError(f"`environment` is one of {', '.join(ENVIRONMENTS)}; the playground never probes production")
    t = Target(**raw)
    if t.preset:
        if t.preset not in PRESETS:
            raise ConfigError(f"`preset` is one of {', '.join(PRESETS)}")
        p = PRESETS[t.preset]
        t.method = raw.get("method", p["method"])
        t.headers = {**p["headers"], **t.headers}
        t.body = t.body if t.body is not None else p["body"]
        t.response = {**p["response"], **t.response}
    if t.kind in ("http", "mcp-http"):
        if not t.url or urllib.parse.urlsplit(t.url).scheme not in ("http", "https"):
            raise ConfigError("`url` must be an http or https address")
        if not host_allowed(t.url, t.allow_hosts):
            host = urllib.parse.urlsplit(t.url).hostname
            raise ConfigError(f"the host {host} is not in `allow_hosts`; list it there to probe it (loopback is always allowed)")
        if t.kind == "http" and t.body is None:
            raise ConfigError("an http target needs a `preset` or a `body` template")
        if t.kind == "http" and not t.response.get("text"):
            raise ConfigError("an http target needs `response.text`: where the answer is in the response")
        if SECRET_REF.search(t.url):
            raise ConfigError("a credential in the url would be logged by every proxy on the way; send it in a header")
    if t.kind in ("command", "mcp-stdio"):
        if not t.command or not all(isinstance(c, str) for c in t.command):
            raise ConfigError("`command` is a list of strings, the program first")
        t.command = [os.path.join(base, c) if c.startswith("./") else c for c in t.command]
    if t.kind == "python":
        if ":" not in t.callable:
            raise ConfigError("`callable` is module:function")
        t.path = os.path.normpath(os.path.join(base, t.path or "."))
        if not os.path.isdir(t.path):
            raise ConfigError(f"`path` is not a directory: {t.path}")
    if t.kind == "demo" and t.demo not in ("safe", "vulnerable"):
        raise ConfigError("`demo` is safe or vulnerable")
    if not all(isinstance(e, str) and re.match(r"^[A-Z_][A-Z0-9_]*$", e) for e in t.env):
        raise ConfigError("`env` lists environment variable names")
    if not (0 < float(t.timeout_s) <= 600):
        raise ConfigError("`timeout_s` is between 0 and 600")
    if not (1 <= int(t.concurrency) <= 32):
        raise ConfigError("`concurrency` is between 1 and 32")
    return t
