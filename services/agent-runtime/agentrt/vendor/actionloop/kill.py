"""Kill switches: run, board and consumer scopes, persisted, read at admit and before every call.

A stop is a state transition the harness reads at its next hook. Named people and a quorum for the consumer-wide switch; every actuation is recorded.
"""
from __future__ import annotations
import sqlite3, time


class KillError(Exception):
    pass


class KillSwitches:
    def __init__(self, conn: sqlite3.Connection, audit, quorum: dict[str, int] | None = None):
        self.conn, self.audit = conn, audit
        self.quorum = quorum or {"run": 1, "board": 1, "consumer": 2}
        conn.execute("CREATE TABLE IF NOT EXISTS kill (scope TEXT, target TEXT, actor TEXT, ts REAL, PRIMARY KEY(scope,target,actor))")
        conn.commit()

    def stop(self, scope: str, target: str, actor: str) -> bool:
        """Register an actor's stop; the switch is active once the quorum is met. Returns whether it is active."""
        if scope not in self.quorum:
            raise KillError("unknown scope")
        self.conn.execute("INSERT OR REPLACE INTO kill VALUES (?,?,?,?)", (scope, target, actor, time.time()))
        self.conn.commit()
        active = self.is_stopped(scope, target)
        self.audit.record(event="kill.actuation", scope=scope, target=target, actor=actor, active=active, consumer=target if scope == "consumer" else None)
        return active

    def clear(self, scope: str, target: str, actor: str) -> None:
        self.conn.execute("DELETE FROM kill WHERE scope=? AND target=?", (scope, target))
        self.conn.commit()
        self.audit.record(event="kill.cleared", scope=scope, target=target, actor=actor)

    def is_stopped(self, scope: str, target: str) -> bool:
        n = self.conn.execute("SELECT COUNT(DISTINCT actor) FROM kill WHERE scope=? AND target=?", (scope, target)).fetchone()[0]
        return n >= self.quorum[scope]

    def state(self, consumer: str, board: str, run_id: str) -> str | None:
        """The first active scope, outermost first, or None."""
        if self.is_stopped("consumer", consumer): return "consumer"
        if self.is_stopped("board", board): return "board"
        if self.is_stopped("run", run_id): return "run"
        return None
