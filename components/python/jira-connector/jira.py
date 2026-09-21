"""Jira as a target behind the harness: read an issue, search, comment, create; a fake behind the same methods.

The client holds no credential: the token is a name resolved from the secrets provider at call time, and every
handler refuses to run without a redeemed reference for its own audience (the credential-helper pattern). A
write carries the acting person's name in its body, so the record in Jira says who asked. Standard library only;
`http` is injected (`json(method, url, headers, payload=None) -> dict`, the stdlib-http-client's).
"""
from __future__ import annotations
import base64, itertools, re, urllib.parse


class JiraError(Exception):
    pass


def require_credential(credential: dict, audience: str) -> str:
    if not credential or credential.get("audience") != audience or not credential.get("on_behalf_of"):
        raise JiraError("no redeemed reference for this audience; the handler will not run")
    return credential["on_behalf_of"]


KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,31}-\d{1,9}$")


def _key(key: str) -> str:
    """An issue key is one path segment: `INC-7`, never `INC-7/../../myself`."""
    if not isinstance(key, str) or not KEY.match(key):
        raise JiraError("not an issue key")
    return urllib.parse.quote(key, safe="")


class JiraClient:
    """Jira Cloud (basic: user email + API token) or Data Center (bearer: a personal access token)."""

    def __init__(self, http, secrets, base_url: str, token_name: str, user: str = "", auth: str = "basic", timeout: float = 15.0):
        if auth not in ("basic", "bearer"):
            raise JiraError("auth must be basic or bearer")
        self.http, self.secrets, self.base, self.token_name, self.user, self.auth = http, secrets, base_url.rstrip("/"), token_name, user, auth

    def _h(self) -> dict:
        token = self.secrets.get(self.token_name)
        value = "Bearer " + token if self.auth == "bearer" else "Basic " + base64.b64encode(f"{self.user}:{token}".encode()).decode()
        return {"Authorization": value, "Accept": "application/json"}

    def _u(self, path: str) -> str:
        return f"{self.base}/rest/api/2/{path}"

    @staticmethod
    def _issue(x: dict) -> dict:
        f = x.get("fields") or {}
        return {"key": x.get("key"), "summary": f.get("summary", ""), "description": f.get("description") or "", "status": (f.get("status") or {}).get("name", ""),
                "assignee": (f.get("assignee") or {}).get("accountId") or (f.get("assignee") or {}).get("name"), "labels": list(f.get("labels") or []), "updated": f.get("updated", "")}

    def get_issue(self, key: str) -> dict:
        return self._issue(self.http.json("GET", self._u(f"issue/{_key(key)}?fields=summary,description,status,assignee,labels,updated"), self._h()))

    def search(self, jql: str, max_results: int = 20) -> list[dict]:
        r = self.http.json("GET", self._u(f"search?jql={urllib.parse.quote(jql)}&maxResults={int(max_results)}&fields=summary,status,assignee,labels,updated"), self._h())
        return [self._issue(x) for x in r.get("issues", [])]

    def add_comment(self, key: str, body: str, acting_human: str) -> dict:
        r = self.http.json("POST", self._u(f"issue/{_key(key)}/comment"), self._h(), {"body": f"{body}\n\n— on behalf of {acting_human}"})
        return {"id": str(r.get("id")), "key": key}

    def create_issue(self, project: str, summary: str, description: str, labels: list, acting_human: str) -> dict:
        r = self.http.json("POST", self._u("issue"), self._h(), {"fields": {"project": {"key": project}, "issuetype": {"name": "Task"}, "summary": summary,
                                                                   "description": f"{description}\n\n— on behalf of {acting_human}", "labels": list(labels)}})
        return {"key": r.get("key"), "id": str(r.get("id"))}


class FakeJira:
    """In memory, the same methods; `down = True` makes every call fail the way an outage does."""

    def __init__(self, issues: dict | None = None):
        self.issues = {k: {"key": k, "summary": v.get("summary", ""), "description": v.get("description", ""), "status": v.get("status", "Open"), "assignee": v.get("assignee"), "labels": list(v.get("labels", [])), "updated": v.get("updated", "")} for k, v in (issues or {}).items()}
        self.comments: list[dict] = []
        self.created: list[dict] = []
        self.down = False
        self._ids = itertools.count(1)

    def _up(self):
        if self.down:
            raise JiraError("jira unavailable")

    def get_issue(self, key: str) -> dict:
        self._up()
        if key not in self.issues:
            raise JiraError(f"no issue {key}")
        return dict(self.issues[key])

    def search(self, jql: str, max_results: int = 20) -> list[dict]:
        self._up()
        return [dict(i) for i in list(self.issues.values())[:max_results]]

    def add_comment(self, key: str, body: str, acting_human: str) -> dict:
        self._up(); self.get_issue(key)
        c = {"id": str(next(self._ids)), "key": key, "body": body, "by": acting_human}
        self.comments.append(c)
        return {"id": c["id"], "key": key}

    def create_issue(self, project: str, summary: str, description: str, labels: list, acting_human: str) -> dict:
        self._up()
        key = f"{project}-{100 + len(self.created) + 1}"
        self.issues[key] = {"key": key, "summary": summary, "description": description, "status": "Open", "assignee": None, "labels": list(labels), "updated": ""}
        self.created.append({"key": key, "by": acting_human})
        return {"key": key, "id": str(next(self._ids))}


def handlers(client, audience: str = "tickets") -> dict:
    """The gateway target: `name -> handler(args, credential)`; the read is R, the comment W1, the create W1."""
    return {
        "get": lambda a, c: (require_credential(c, audience), client.get_issue(a["key"]))[1],
        "search": lambda a, c: (require_credential(c, audience), {"issues": client.search(a["jql"], int(a.get("max", 20)))})[1],
        "comment": lambda a, c: client.add_comment(a["key"], a["body"], require_credential(c, audience)),
        "create": lambda a, c: client.create_issue(a["project"], a["summary"], a.get("description", ""), a.get("labels", []), require_credential(c, audience)),
    }
