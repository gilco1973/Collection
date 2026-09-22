"""    python3 -m agentrt check-config     # exit 0 on config ok, 2 with every problem named; the entrypoint's first command
    python3 -m agentrt serve            # MCP on /mcp, the run API on /runs, /health
    python3 -m agentrt export-audit     # the chain to AGENT_AUDIT_EXPORT (run nightly, and before a task is retired)
    python3 -m agentrt verify-record    # walk the chain in AGENT_DB; exit 1 on a break
    python3 -m agentrt token <user>     # sandbox only: a token from the fake identity provider
    python3 -m agentrt backup <path>    # a consistent copy of the record (SQLite online backup) for the bank's backup job
    python3 -m agentrt stop <scope> <target> --by <person>     # a kill switch: run, board or consumer; recorded on the chain
    python3 -m agentrt resume <scope> <target> --by <person>   # a vote to clear it (the consumer scope needs two people)
A record from a newer build or a failed export is one named line and exit 2 (1 for a broken chain). A missing record
is created by verify-record and serve (the first start); only backup refuses it, with a named line and exit 2.
"""
from __future__ import annotations
import json, logging, os, sqlite3, sys
from .app import serve
from .ops import install_logging
from .settings import ConfigError, Settings, check_config
from .wiring import RecordError, UrllibHttp, build, open_record, open_switches


def record_file_problem(cmd: str, s) -> str | None:
    """Why a command that reads the record file cannot: the path is not a file. None when it is one."""
    if s.db_path == ":memory:" or not os.path.exists(s.db_path):
        return f"{cmd}: the record does not exist: {s.prefix}DB={s.db_path}"
    if not os.path.isfile(s.db_path):
        return f"{cmd}: the record is not a file: {s.prefix}DB={s.db_path}"
    return None


def kill_target(rec, scope: str, target: str) -> tuple:
    """The target the harness checks, from what an operator has: a run is named by its session id (what the API
    and the logs show) and resolved to the run id in the record; the consumer is `-`, `self` or the exact harness
    consumer, never the template name (the harness checks `agent:<name>`). Returns (target, problem)."""
    if scope == "run":
        j = rec.sessions.load_json(target)
        if not j or not j.get("run_id"):
            return None, f"unknown session: {target} (a run is stopped by its session id)"
        return j["run_id"], None
    if scope == "consumer":
        if target in ("-", "self", rec.consumer):
            return rec.consumer, None
        return None, f"the consumer scope takes -, self or {rec.consumer}, not {target}"
    return target, None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "serve"
    if cmd == "check-config":
        return check_config()
    s = Settings.from_env()
    install_logging(s.log_level)
    if cmd == "backup":
        if len(argv) < 2 or s.db_path == ":memory:":
            print("usage: backup <path>; the record must be a file (AGENT_DB)"); return 2
        problem = record_file_problem(cmd, s)
        if problem:
            print(problem); return 2
        try:
            src = open_record(s.db_path, readonly=True)  # read-only: a backup never migrates the live record
            dst = sqlite3.connect(argv[1])
            src.backup(dst); pages = dst.execute("PRAGMA page_count").fetchone()[0]; dst.close(); src.close()
        except RecordError as e:
            print("record:", e); return 2
        except sqlite3.Error as e:  # the record cannot be opened or the copy cannot be written: named, never a traceback
            print(f"backup failed: {type(e).__name__}: {e}"); return 2
        print(f"backup written: {argv[1]} ({pages} pages)"); return 0
    if cmd == "verify-record":
        from actionloop.audit import AuditChain
        if s.db_path == ":memory:" or not os.path.exists(s.db_path):
            print("record: none yet (a first start creates it)"); return 0  # the entrypoint verifies before serve: serve creates the record, this never does
        problem = record_file_problem(cmd, s)
        if problem:
            print(problem); return 2
        try:
            conn = open_record(s.db_path, readonly=True)  # read-only: verifying never migrates the record
            if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit'").fetchone():
                conn.close(); print("record ok: 0 records (no chain yet)"); return 0
            n = AuditChain(conn).verify(); conn.close()
        except RecordError as e:
            print("record:", e); return 2
        except sqlite3.Error as e:
            print(f"record: cannot be read: {type(e).__name__}: {e}"); return 2
        except Exception as e:
            print("record broken:", type(e).__name__); return 1
        print(f"record ok: {n} records"); return 0
    if cmd in ("stop", "resume"):
        from actionloop.identity import Human
        if len(argv) < 3 or "--by" not in argv or argv.index("--by") + 1 >= len(argv):
            print(f"usage: {cmd} <run|board|consumer> <target> --by <person>"); return 2
        who = Human(argv[argv.index("--by") + 1], argv[argv.index("--by") + 1], ("operator",))
        try:
            w = open_switches(s)  # the record alone: the switch is thrown while the identity provider or KMS is down
        except (RecordError, sqlite3.Error, OSError) as e:
            print("record:", e); return 2
        target, problem = kill_target(w, argv[1], argv[2])
        if problem:
            print(f"{cmd} refused: {problem}"); return 2
        try:
            (w.kills.stop if cmd == "stop" else w.kills.clear)(argv[1], target, who)
            active = w.kills.is_stopped(argv[1], target)   # the switch's state after the vote, not the vote's return value (clear() answers "still active" to a lone vote on a switch that was never on)
        except Exception as e:  # noqa: BLE001 - an unknown scope
            print(f"{cmd} refused: {type(e).__name__}: {e}"); return 2
        print(f"{argv[1]} {target}: {'stopped' if active else 'running'} (recorded on the chain, by {who.id})"); return 0
    if cmd == "token" and s.identity != "fake":
        print("token: sandbox only (the fake identity provider)"); return 2
    try:
        w = build(s)
    except RecordError as e:
        print("record:", e); return 2
    except ConfigError as e:
        print("config:", e); return 2
    except (RuntimeError, OSError) as e:  # the identity provider, the key service or a target could not be reached: the class, never a traceback
        print(f"{cmd}: the runtime could not be built: {type(e).__name__}"); return 2
    if cmd == "token":
        print(w.token(argv[1] if len(argv) > 1 else "u_dana")); return 0
    if cmd == "export-audit":
        from .export import S3Put, export_chain
        if not s.audit_export:
            print("AGENT_AUDIT_EXPORT is empty; nothing exported"); return 2
        try:
            print(json.dumps(export_chain(w.audit, w.template["name"], s.audit_export, S3Put(UrllibHttp(30.0), s.bedrock_region or os.environ.get("AWS_REGION", "")), work_dir=work_dir_for(s)))); return 0
        except Exception as e:  # noqa: BLE001 - the bucket, the network or the credentials; the class names it, the chain is still local
            print("export failed:", type(e).__name__); return 2
    if cmd != "serve":
        print(__doc__); return 2
    httpd = serve(w, s.listen_host, s.listen_port, s.public_url)
    import signal, threading
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown, daemon=True).start())
    if s.audit_export and s.audit_export_interval_s:
        threading.Thread(target=export_loop, args=(w, s), daemon=True).start()
    logging.getLogger("agentrt").info("listening agent=%s env=%s port=%d diagnostics=%s", w.template["name"], s.env, s.listen_port, json.dumps(s.diagnostics()))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    from .app import drain
    if not drain(httpd, 25.0):  # the ECS stop timeout is 30 s; a run still going after that is cut by the platform
        logging.getLogger("agentrt").warning("stopped with a request still in flight")
    return 0


def work_dir_for(s) -> str | None:
    """Scratch space beside the record: the task's root filesystem is read-only and only the record volume is writable."""
    d = os.path.dirname(os.path.abspath(s.db_path)) if s.db_path and s.db_path != ":memory:" else None
    return d if d and os.path.isdir(d) and os.access(d, os.W_OK) else None


def export_loop(w, s, stop=None, sleep=None, put=None):
    """Exports the chain every interval from inside the task. A failure is logged and retried next time; nothing is lost, the chain is still local."""
    import time
    from .export import S3Put, export_chain
    put = put or S3Put(UrllibHttp(30.0), s.bedrock_region or os.environ.get("AWS_REGION", ""))
    wait = sleep or time.sleep
    while not (stop and stop.is_set()):
        wait(s.audit_export_interval_s)
        if stop and stop.is_set(): break
        try:
            out = export_chain(w.audit, w.template["name"], s.audit_export, put, work_dir=work_dir_for(s))
            logging.getLogger("agentrt").info("audit exported records=%s head=%s", out.get("records"), out.get("head"))
        except Exception as e:
            logging.getLogger("agentrt").warning("audit export failed error=%s; the chain stays local until the next interval", type(e).__name__)


if __name__ == "__main__":
    sys.exit(main())
