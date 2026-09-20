"""    python3 -m agentrt check-config     # exit 0 on config ok, 2 with every problem named; the entrypoint's first command
    python3 -m agentrt serve            # MCP on /mcp, the run API on /runs, /health
    python3 -m agentrt export-audit     # the chain to AGENT_AUDIT_EXPORT (run nightly, and before a task is retired)
    python3 -m agentrt verify-record    # walk the chain in AGENT_DB; exit 1 on a break
    python3 -m agentrt token <user>     # sandbox only: a token from the fake identity provider
    python3 -m agentrt backup <path>    # a consistent copy of the record (SQLite online backup) for the bank's backup job
"""
from __future__ import annotations
import json, logging, os, sys
from .app import serve
from .ops import install_logging
from .settings import Settings, check_config
from .wiring import UrllibHttp, build


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "serve"
    if cmd == "check-config":
        return check_config()
    s = Settings.from_env()
    install_logging(s.log_level)
    if cmd == "backup":
        import sqlite3
        if len(argv) < 2 or s.db_path == ":memory:":
            print("usage: backup <path>; the record must be a file (AGENT_DB)"); return 2
        src, dst = sqlite3.connect(s.db_path), sqlite3.connect(argv[1])
        src.backup(dst); pages = dst.execute("PRAGMA page_count").fetchone()[0]; dst.close(); src.close()
        print(f"backup written: {argv[1]} ({pages} pages)"); return 0
    if cmd == "verify-record":
        from actionloop.audit import AuditChain
        import sqlite3
        try:
            n = AuditChain(sqlite3.connect(s.db_path)).verify()
        except Exception as e:
            print("record broken:", type(e).__name__); return 1
        print(f"record ok: {n} records"); return 0
    w = build(s)
    if cmd == "token":
        print(w.token(argv[1] if len(argv) > 1 else "u_dana")); return 0
    if cmd == "export-audit":
        from .export import S3Put, export_chain
        if not s.audit_export:
            print("AGENT_AUDIT_EXPORT is empty; nothing exported"); return 2
        print(json.dumps(export_chain(w.audit, w.template["name"], s.audit_export, S3Put(UrllibHttp(30.0), s.bedrock_region or os.environ.get("AWS_REGION", ""))))); return 0
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
    return 0


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
            out = export_chain(w.audit, w.template["name"], s.audit_export, put)
            logging.getLogger("agentrt").info("audit exported records=%s head=%s", out.get("records"), out.get("head"))
        except Exception as e:
            logging.getLogger("agentrt").warning("audit export failed error=%s; the chain stays local until the next interval", type(e).__name__)


if __name__ == "__main__":
    sys.exit(main())
