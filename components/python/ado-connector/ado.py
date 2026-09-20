"""Azure DevOps as a target behind the harness: recent pipeline runs, one run, run a pipeline (a rollback, W2);
a fake behind the same methods.

The client holds no credential (a PAT name resolved at call time); handlers refuse to run without a redeemed
reference for their audience; a write carries the acting person. `latest_deploy` shapes the last finished run
the way an incident agent reads it: run id, service and minutes before the trigger. Standard library only;
`http` is injected (`json(method, url, headers, payload=None) -> dict`).
"""
from __future__ import annotations
import base64, datetime as _dt, urllib.parse


class AdoError(Exception):
    pass


def require_credential(credential: dict, audience: str) -> str:
    if not credential or credential.get("audience") != audience or not credential.get("on_behalf_of"):
        raise AdoError("no redeemed reference for this audience; the handler will not run")
    return credential["on_behalf_of"]


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class AdoClient:
    def __init__(self, http, secrets, org_url: str, project: str, pat_name: str):
        self.http, self.secrets, self.org, self.project, self.pat_name = http, secrets, org_url.rstrip("/"), project, pat_name

    def _h(self) -> dict:
        return {"Authorization": "Basic " + base64.b64encode(f":{self.secrets.get(self.pat_name)}".encode()).decode(), "Accept": "application/json"}

    def _u(self, path: str, q: str = "") -> str:
        return f"{self.org}/{urllib.parse.quote(self.project)}/_apis/{path}?api-version=7.1{q}"

    @staticmethod
    def _run(x: dict) -> dict:
        return {"id": x.get("id"), "name": x.get("name"), "state": x.get("state"), "result": x.get("result"), "created": x.get("createdDate"), "finished": x.get("finishedDate"),
                "url": ((x.get("_links") or {}).get("web") or {}).get("href")}

    def recent_runs(self, pipeline_id: int, top: int = 10) -> dict:
        r = self.http.json("GET", self._u(f"pipelines/{int(pipeline_id)}/runs", f"&$top={int(top)}"), self._h())
        return {"pipeline": int(pipeline_id), "runs": [self._run(x) for x in r.get("value", [])]}

    def get_run(self, pipeline_id: int, run_id: int) -> dict:
        return self._run(self.http.json("GET", self._u(f"pipelines/{int(pipeline_id)}/runs/{int(run_id)}"), self._h()))

    def latest_deploy(self, pipeline_id: int, service: str, trigger_ts: float) -> dict:
        runs = [r for r in self.recent_runs(pipeline_id, 10)["runs"] if r.get("result") == "succeeded" and _ts(r.get("finished")) is not None]
        if not runs:
            return {"run_id": None, "service": service, "minutes_before_trigger": None, "notes": "no finished run"}
        last = max(runs, key=lambda r: _ts(r["finished"]))
        return {"run_id": last["id"], "service": service, "minutes_before_trigger": int((trigger_ts - _ts(last["finished"])) // 60), "notes": last.get("name") or ""}

    def run_pipeline(self, pipeline_id: int, acting_human: str, variables: dict, reason: str) -> dict:
        body = {"variables": {k: {"value": str(v)} for k, v in variables.items()}, "templateParameters": {}, "resources": {},
                "previewRun": False}
        body["variables"]["requestedBy"] = {"value": acting_human}; body["variables"]["reason"] = {"value": reason}
        r = self.http.json("POST", self._u(f"pipelines/{int(pipeline_id)}/runs"), self._h(), body)
        return {"run_id": r.get("id"), "status": r.get("state", "started")}


class FakeAdo:
    """In memory, the same methods; seed runs per pipeline; `down = True` makes every call fail."""

    def __init__(self):
        self.runs: dict[int, list[dict]] = {}
        self.started: list[dict] = []
        self.down = False

    def seed(self, pipeline_id: int, runs: list[dict]) -> None:
        self.runs[pipeline_id] = [dict(r) for r in runs]

    def _up(self):
        if self.down:
            raise AdoError("azure devops unavailable")

    def recent_runs(self, pipeline_id: int, top: int = 10) -> dict:
        self._up(); return {"pipeline": pipeline_id, "runs": list(self.runs.get(pipeline_id, []))[:top]}

    def get_run(self, pipeline_id: int, run_id: int) -> dict:
        self._up()
        for r in self.runs.get(pipeline_id, []):
            if r["id"] == run_id:
                return dict(r)
        raise AdoError(f"no run {run_id}")

    latest_deploy = AdoClient.latest_deploy

    def run_pipeline(self, pipeline_id: int, acting_human: str, variables: dict, reason: str) -> dict:
        self._up()
        run = {"id": 9000 + len(self.started) + 1, "name": "rollback", "state": "inProgress", "result": None, "created": "", "finished": None, "url": None}
        self.runs.setdefault(pipeline_id, []).insert(0, run); self.started.append({"pipeline": pipeline_id, "by": acting_human, "variables": dict(variables), "reason": reason})
        return {"run_id": run["id"], "status": "started"}


def handlers(client, audience: str = "deploys", pipelines: dict | None = None) -> dict:
    """The gateway target. `pipelines` maps a service name to its pipeline id; a service not in it is refused."""
    pipelines = dict(pipelines or {})

    def pipeline(service: str) -> int:
        if service not in pipelines:
            raise AdoError(f"no pipeline is recorded for service {service!r}")
        return pipelines[service]

    return {
        "recent": lambda a, c: (require_credential(c, audience), client.latest_deploy(pipeline(a["service"]), a["service"], float(a.get("trigger_ts") or __import__("time").time())))[1],
        "runs": lambda a, c: (require_credential(c, audience), client.recent_runs(pipeline(a["service"]), int(a.get("top", 10))))[1],
        "rollback": lambda a, c: client.run_pipeline(pipeline(a["service"]), require_credential(c, audience), {"target_run": a["run_id"], "action": "rollback"}, a.get("reason", "rollback")),
    }
