"""    python3 -m hubapi check-config      # exit 0 on config ok, 2 with every problem listed; the entrypoint's first command
    python3 -m hubapi serve             # the hub API (and the hub itself when HUB_STATIC_DIR points at its dist/)
    python3 -m hubapi mock-token <persona>   # a mock bearer for development (refused in production)
    python3 -m hubapi backup <path>     # a consistent copy of the record (SQLite online backup, source opened read-only) for the bank's backup job
    python3 -m hubapi prune             # apply the retention now (serve does it daily): conversations past HUB_CONVERSATION_RETENTION_DAYS and replays past HUB_IDEMPOTENCY_TTL_S

Every command exits 2 with a `config:` line when the configuration is refused and with a `record:` line when the
record was written by a newer build; a traceback is never the answer.
"""
from __future__ import annotations
import json, logging, os, sys, threading, urllib.request
from .app import HubApi, drain, serve
from .assistant import build as build_assistant
from .auth import IdentityMap, MockAuth, OidcAuth
from .catalog import Catalog
from .ops import install_logging
from .settings import SERVICE, ConfigError, Settings, check_config
from .store import Store, StoreError

DRAIN_S = 25.0          # after SIGTERM: how long in-flight requests (a turn mid-stream) may take to finish before the process exits
FIRST_RETENTION_S = 60  # the retention runs once shortly after start, then daily: a task that lives a day never skips it


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def secrets_for(s: Settings):
    from .vendor import secretsbyname as S
    def aws_factory():
        from .vendor.sigv4 import AwsJson
        from .assistant import UrllibHttp
        return AwsJson(UrllibHttp(15.0), s.bedrock_region or os.environ.get("AWS_REGION", ""))
    os.environ[s.prefix + "SECRETS"] = s.secrets
    return S.provider_from_env(aws_factory, s.prefix)


def build(s: Settings) -> HubApi:
    s.require_valid()
    catalog = Catalog.load(s.consumers_file, s.collection_file)
    if s.auth == "mock":
        personas = json.load(open(os.path.join(SERVICE, "data", "examples.json"), encoding="utf-8"))["principals"]
        auth = MockAuth(personas)
    else:
        auth = OidcAuth(s.idp_issuer, s.idp_audience, s.idp_jwks_url, fetch_json, IdentityMap.load(s.identity_map), s.ai_security_group)
    from .guide import build as build_guide
    return HubApi(s, Store(s.db_path, s.idempotency_ttl_s), catalog, auth, build_assistant(s, secrets_for(s)), build_guide(s))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "serve"
    if cmd == "check-config":
        return check_config()
    s = Settings.from_env()
    try:
        return run(cmd, argv, s)
    except ConfigError as e:
        for line in str(e).split("; "): print("config:", line)
        return 2
    except StoreError as e:  # a record written by a newer build: named, never a traceback; see the runbook, "When it will not start"
        print("record:", e); return 2


def _record_file(s: Settings, cmd: str) -> str | None:
    """The record's path for a command that works on the file itself; a problem line and None when there is none."""
    if s.db_path == ":memory:":
        print(f"config: {s.prefix}DB is :memory:; {cmd} needs the record file"); return None
    if not os.path.isfile(s.db_path):
        print(f"{cmd}: the record does not exist: {s.prefix}DB"); return None
    return s.db_path


def run(cmd: str, argv: list, s: Settings) -> int:
    if cmd == "backup":
        if len(argv) < 2:
            print("usage: backup <path>"); return 2
        s.require_valid()
        path = _record_file(s, "backup")
        if not path: return 2
        pages = Store.backup_file(path, argv[1])   # read-only source: a backup never migrates the live record
        print(f"backup written: {argv[1]} ({pages} pages)"); return 0
    if cmd == "prune":
        s.require_valid()
        path = _record_file(s, "prune")
        if not path: return 2
        install_logging(s.log_level)
        store = Store(path, s.idempotency_ttl_s)
        try:
            n, replays = retention_counts(store, s)
        finally:
            store.close()
        print(f"pruned: {n} conversations past {s.conversation_retention_days} days, {replays} replays past {s.idempotency_ttl_s} s"); return 0
    if cmd == "mock-token":
        if s.live or s.auth != "mock":
            print("mock tokens exist only with HUB_AUTH=mock in the sandbox"); return 2
        print(f"mock.{argv[1] if len(argv) > 1 else 'gk'}"); return 0
    if cmd != "serve":
        print(__doc__); return 2
    s.require_valid()
    install_logging(s.log_level)
    api = build(s)
    httpd = serve(api, s.listen_host, s.listen_port, s.static_dir)
    threading.Thread(target=retention_loop, args=(api.store, s), daemon=True).start()
    import signal
    # A rolling deploy: stop accepting, let the requests in flight finish (a turn mid-stream is written to the record), then exit 0.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown, daemon=True).start())
    logging.getLogger("hubapi").info("listening env=%s auth=%s assistant=%s port=%d static=%s diagnostics=%s", s.env, s.auth, api.assistant.name, s.listen_port, bool(s.static_dir), json.dumps(s.diagnostics()))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    stop(httpd, api.store)
    return 0


def stop(httpd, store: Store, drain_s: float = DRAIN_S) -> bool:
    """After the server loop ends: in-flight handlers get `drain_s` to finish, then the record is closed so a clean
    stop checkpoints and removes the WAL (a restore beside a stale `-wal` would replay it over the restored file)."""
    finished = drain(httpd, drain_s)
    if not finished:
        logging.getLogger("hubapi").warning("stopped with requests still in flight after %.0fs inflight=%d", drain_s, httpd.inflight)
    httpd.server_close()
    try:
        store.close()
    except Exception as e:  # noqa: BLE001 - a handler past the grace still holding the connection
        logging.getLogger("hubapi").warning("record close failed error=%s", type(e).__name__)
    return finished


def retention_counts(store: Store, s: Settings, now: float | None = None) -> tuple[int, int]:
    """(conversations deleted, replays forgotten): conversations (and their feedback) older than the retention, 0 keeps
    them; idempotency replays older than HUB_IDEMPOTENCY_TTL_S always."""
    replays = store.prune(now)
    if not s.conversation_retention_days:
        return 0, replays
    return store.prune_docs("conversation", s.conversation_retention_days * 86_400, now), replays


def retention(store: Store, s: Settings, now: float | None = None) -> int:
    """Deletes conversations (and their feedback) older than the retention; 0 keeps everything. Replays are pruned too."""
    return retention_counts(store, s, now)[0]


def retention_loop(store: Store, s: Settings, stop=None, sleep=None, first_delay_s: float = FIRST_RETENTION_S):
    """Once shortly after start, then once a day, from inside the task; a failure is logged and tried again tomorrow."""
    import time
    wait = sleep or time.sleep
    delay = first_delay_s
    while not (stop and stop.is_set()):
        wait(delay); delay = 86_400
        try:
            n, replays = retention_counts(store, s)
            logging.getLogger("hubapi").info("retention applied conversations_deleted=%d days=%d replays_deleted=%d", n, s.conversation_retention_days, replays)
        except Exception as e:
            logging.getLogger("hubapi").warning("retention failed error=%s", type(e).__name__)


if __name__ == "__main__":
    sys.exit(main())
