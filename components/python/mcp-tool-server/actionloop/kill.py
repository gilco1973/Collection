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
        conn.execute("CREATE TABLE IF NOT EXISTS kill_clear (scope TEXT, target TEXT, actor TEXT, ts REAL, PRIMARY KEY(scope,target,actor))")
        conn.commit()

    @staticmethod
    def _who(actor) -> str:
        """The actor is a resolved person (a Human or a PrincipalChain from the identity library), never a string a
        caller typed: the quorum counts people, and the record names them."""
        human = getattr(actor, "human", actor)
        hid = getattr(human, "id", None)
        if not isinstance(hid, str) or not hid or not hasattr(human, "roles"):
            raise KillError("the actor must be a resolved person (Human or PrincipalChain)")
        return hid

    def stop(self, scope: str, target: str, actor) -> bool:
        """Register a person's stop; the switch is active once the quorum is met. Returns whether it is active."""
        if scope not in self.quorum:
            raise KillError("unknown scope")
        who = self._who(actor)
        self.conn.execute("INSERT OR REPLACE INTO kill VALUES (?,?,?,?)", (scope, target, who, time.time()))
        self.conn.execute("DELETE FROM kill_clear WHERE scope=? AND target=?", (scope, target))  # a new stop needs a new quorum to clear
        self.conn.commit()
        active = self.is_stopped(scope, target)
        self.audit.record(event="kill.actuation", scope=scope, target=target, actor=who, active=active, consumer=target if scope == "consumer" else None)
        return active

    def clear(self, scope: str, target: str, actor) -> bool:
        """A person's vote to clear; the switch is released once as many distinct people as the scope's quorum voted.
        Returns whether the switch is still active."""
        if scope not in self.quorum:
            raise KillError("unknown scope")
        who = self._who(actor)
        self.conn.execute("INSERT OR REPLACE INTO kill_clear VALUES (?,?,?,?)", (scope, target, who, time.time()))
        n = self.conn.execute("SELECT COUNT(DISTINCT actor) FROM kill_clear WHERE scope=? AND target=?", (scope, target)).fetchone()[0]
        released = n >= self.quorum[scope]
        if released:
            self.conn.execute("DELETE FROM kill WHERE scope=? AND target=?", (scope, target))
            self.conn.execute("DELETE FROM kill_clear WHERE scope=? AND target=?", (scope, target))
        self.conn.commit()
        self.audit.record(event="kill.cleared" if released else "kill.clear_vote", scope=scope, target=target, actor=who, votes=n)
        return not released

    def is_stopped(self, scope: str, target: str) -> bool:
        n = self.conn.execute("SELECT COUNT(DISTINCT actor) FROM kill WHERE scope=? AND target=?", (scope, target)).fetchone()[0]
        return n >= self.quorum[scope]

    def state(self, consumer: str, board: str, run_id: str) -> str | None:
        """The first active scope, outermost first, or None."""
        if self.is_stopped("consumer", consumer): return "consumer"
        if self.is_stopped("board", board): return "board"
        if self.is_stopped("run", run_id): return "run"
        return None
