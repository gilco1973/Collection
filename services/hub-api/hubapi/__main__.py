"""    python3 -m hubapi check-config      # exit 0 on config ok, 2 with every problem listed; the entrypoint's first command
    python3 -m hubapi serve             # the hub API (and the hub itself when HUB_STATIC_DIR points at its dist/)
    python3 -m hubapi mock-token <persona>   # a mock bearer for development (refused in production)
"""
from __future__ import annotations
import json, logging, os, sys, threading, urllib.request
from .app import HubApi, serve
from .assistant import build as build_assistant
from .auth import IdentityMap, MockAuth, OidcAuth
from .catalog import Catalog
from .settings import SERVICE, Settings, check_config
from .store import Store


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
    return HubApi(s, Store(s.db_path), catalog, auth, build_assistant(s, secrets_for(s)))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "serve"
    if cmd == "check-config":
        return check_config()
    s = Settings.from_env()
    logging.basicConfig(level=getattr(logging, s.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if cmd == "mock-token":
        if s.env == "production" or s.auth != "mock":
            print("mock tokens exist only with HUB_AUTH=mock outside production"); return 2
        print(f"mock.{argv[1] if len(argv) > 1 else 'gk'}"); return 0
    if cmd != "serve":
        print(__doc__); return 2
    api = build(s)
    httpd = serve(api, s.listen_host, s.listen_port, s.static_dir)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown, daemon=True).start())  # a rolling deploy: finish in-flight requests, then exit 0
    logging.getLogger("hubapi").info("listening env=%s auth=%s assistant=%s port=%d static=%s diagnostics=%s", s.env, s.auth, api.assistant.name, s.listen_port, bool(s.static_dir), json.dumps(s.diagnostics()))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
