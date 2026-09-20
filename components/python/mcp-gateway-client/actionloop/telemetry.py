"""Telemetry: spend per consumer, board, ticket and phase; "not measured" is a distinct state.

Model working time is what the adapter reports, never wall time. A phase with no measurement is absent
(None), never zero; totals are cumulative across attempts. Units are metered per session and per
gateway call so an operate report has a cost line to reconcile against the real bill.
"""
from __future__ import annotations
import sqlite3
from collections import defaultdict

# Reported unit prices: placeholders to re-verify against the real bill before the cost model is signed
UNIT_PRICES = {"runtime_vcpu_h": 0.0895, "runtime_gb_h": 0.00945, "gateway_call": 0.000005, "model_tokens_1k": 0.003}


class Telemetry:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.execute("""CREATE TABLE IF NOT EXISTS spend (consumer TEXT, board TEXT, ticket TEXT, phase TEXT, kind TEXT,
                        input_tokens INTEGER, output_tokens INTEGER, model_ms INTEGER, model_id TEXT, units REAL)""")
        conn.execute("CREATE TABLE IF NOT EXISTS metrics (name TEXT, consumer TEXT, value REAL, ts REAL)")
        conn.commit()

    def model_call(self, consumer, board, ticket, phase, tin, tout, ms, model_id):
        self.conn.execute("INSERT INTO spend VALUES (?,?,?,?,?,?,?,?,?,?)", (consumer, board, ticket, phase, "model", tin, tout, ms, model_id, (tin + tout) / 1000 * UNIT_PRICES["model_tokens_1k"]))
        self.conn.commit()

    def gateway_call(self, consumer, board, ticket, phase):
        self.conn.execute("INSERT INTO spend VALUES (?,?,?,?,?,?,?,?,?,?)", (consumer, board, ticket, phase, "gateway", None, None, None, None, UNIT_PRICES["gateway_call"]))
        self.conn.commit()

    def runtime_session(self, consumer, board, ticket, vcpu_h: float, gb_h: float):
        self.conn.execute("INSERT INTO spend VALUES (?,?,?,?,?,?,?,?,?,?)", (consumer, board, ticket, "overhead", "runtime", None, None, None, None, vcpu_h * UNIT_PRICES["runtime_vcpu_h"] + gb_h * UNIT_PRICES["runtime_gb_h"]))
        self.conn.commit()

    def metric(self, name: str, consumer: str, value: float):
        import time
        self.conn.execute("INSERT INTO metrics VALUES (?,?,?,?)", (name, consumer, value, time.time()))
        self.conn.commit()


    def ticket_breakdown(self, ticket: str) -> dict:
        """Per phase: tokens and model time, or 'not measured' when no model row exists for the phase."""
        phases = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "model_ms": 0, "measured": False, "units": 0.0})
        for phase, kind, tin, tout, ms, units in self.conn.execute("SELECT phase, kind, input_tokens, output_tokens, model_ms, units FROM spend WHERE ticket=?", (ticket,)):
            p = phases[phase]
            p["units"] += units or 0.0
            if kind == "model":
                p["measured"] = True; p["input_tokens"] += tin or 0; p["output_tokens"] += tout or 0; p["model_ms"] += ms or 0
        out = {}
        for ph, p in phases.items():
            out[ph] = {"units": round(p["units"], 6), "tokens": (p["input_tokens"] + p["output_tokens"]) if p["measured"] else None,
                       "model_ms": p["model_ms"] if p["measured"] else None, "state": "measured" if p["measured"] else "not measured"}
        return out

    def cost_per_ticket(self, board: str) -> dict:
        rows = self.conn.execute("SELECT ticket, SUM(units) FROM spend WHERE board=? AND ticket IS NOT NULL GROUP BY ticket", (board,)).fetchall()
        return {t: round(u, 6) for t, u in rows}
