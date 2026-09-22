"""The playground's own record: saved targets and every run's report, in one data directory.

    <data>/targets/<name>.json      the target files, as the tester wrote them (credentials are names, never values)
    <data>/playground.db            runs: id, target, verdict, when, by, and the report itself
    <data>/reports/<id>.{json,md,html}

SQLite from the standard library; one writer at a time through a lock, so the web server's threads share it. A
triage holds the lock from reading the run to writing it back, so two people triaging at once both keep their
decision. A decision recorded on `<data>/reports/<id>.json` with the command line is adopted before the page's
next triage (when the file's verified log extends the database's); when the two logs disagree, the page refuses
instead of overwriting either.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading

from . import config as C
from . import report as Rp

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, started TEXT NOT NULL, target TEXT, component TEXT, verdict TEXT NOT NULL,
  by TEXT, role TEXT, report TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_started ON runs(started);
"""


class Store:
    def __init__(self, data_dir: str):
        self.dir = os.path.abspath(data_dir)
        os.makedirs(os.path.join(self.dir, "targets"), exist_ok=True)
        os.makedirs(os.path.join(self.dir, "reports"), exist_ok=True)
        self.lock = threading.RLock()   # re-entrant: triage holds it across run() and add_run()
        self.db = sqlite3.connect(os.path.join(self.dir, "playground.db"), check_same_thread=False)
        self.db.executescript(SCHEMA)

    # targets --------------------------------------------------------------------------------------------------------
    def target_path(self, name: str) -> str:
        if not C.NAME.match(name or ""):
            raise C.ConfigError("a target name is lower case letters, digits, dot, dash or underscore")
        return os.path.join(self.dir, "targets", name + ".json")

    def targets(self) -> list:
        out = []
        for f in sorted(os.listdir(os.path.join(self.dir, "targets"))):
            if f.endswith(".json"):
                path = os.path.join(self.dir, "targets", f)
                try:
                    out.append({"file": f, "target": C.load(path).describe(), "error": None})
                except C.ConfigError as e:
                    out.append({"file": f, "target": None, "error": str(e)})
        return out

    def raw_target(self, name: str) -> dict:
        with open(self.target_path(name), encoding="utf-8") as f:
            return json.load(f)

    def save_target(self, raw: dict) -> C.Target:
        t = C.load(raw)                       # validate before anything is written
        path = self.target_path(t.name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2)
        os.replace(tmp, path)
        return C.load(path)

    def load_target(self, name: str) -> C.Target:
        path = self.target_path(name)
        if not os.path.exists(path):
            raise C.ConfigError(f"no target named {name}")
        return C.load(path)

    def delete_target(self, name: str) -> bool:
        path = self.target_path(name)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    # runs -----------------------------------------------------------------------------------------------------------
    def add_run(self, rep: dict) -> dict:
        with self.lock:
            paths = Rp.save(rep, os.path.join(self.dir, "reports"))
            self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)",
                            (rep["id"], rep["started"], (rep.get("target") or {}).get("name"), (rep.get("component") or {}).get("name"),
                             rep["verdict"], rep["tester"].get("by"), rep["tester"].get("role"), json.dumps(rep)))
            self.db.commit()
        return paths

    def runs(self, limit: int = 100) -> list:
        with self.lock:
            rows = self.db.execute("SELECT id, started, target, component, verdict, by, role, report FROM runs ORDER BY started DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for rid, started, target, comp, verdict, by, role, rep in rows:
            summary = json.loads(rep)["summary"]["by_status"]
            out.append({"id": rid, "started": started, "target": target, "component": comp, "verdict": verdict, "by": by, "role": role, "counts": summary})
        return out

    def run(self, rid: str) -> dict | None:
        with self.lock:
            row = self.db.execute("SELECT report FROM runs WHERE id = ?", (rid,)).fetchone()
        return json.loads(row[0]) if row else None

    def report_path(self, rid: str) -> str:
        return os.path.join(self.dir, "reports", os.path.basename(rid) + ".json")

    def current(self, rid: str) -> dict | None:
        """The run as the database has it, or as its report file has it when a decision was recorded on the file
        (with the command line) that the database has not seen. ValueError when the two logs disagree, or the file no
        longer verifies: neither is overwritten."""
        with self.lock:
            rep = self.run(rid)
            path = self.report_path(rid)
            if rep is None or not os.path.exists(path):
                return rep
            try:
                on_file = Rp.load(path)
            except ValueError as e:
                raise ValueError(f"the report file does not verify ({e}); move it aside to triage from the playground's own record") from None
            if on_file.get("id") != rep["id"]:
                raise ValueError(f"the report file {path} holds another report; move it aside to triage from the playground's own record")
            if Rp.extends(rep.get("triage"), on_file.get("triage")):
                return on_file   # the file's log is the database's plus decisions recorded on the file
            if Rp.extends(on_file.get("triage"), rep.get("triage")):
                return rep       # the file is behind: it is rewritten from the database
            raise ValueError(f"the triage recorded on {path} and in the playground's record disagree; "
                             "nothing was written. Decide which one stands and move the other aside")

    def triage(self, rid: str, result_id: str, decision: str, by: str, reason: str) -> dict:
        with self.lock:   # read, decide and write as one step: a decision recorded meanwhile is never overwritten
            rep = self.current(rid)
            if rep is None:
                raise KeyError(rid)
            Rp.triage(rep, result_id, decision, by, reason)
            self.add_run(rep)
        return rep
