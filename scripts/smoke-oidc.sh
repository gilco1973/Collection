#!/bin/sh
# The real sign-in path, end to end, with no mock anywhere: a stand-in OpenID Connect provider over TLS
# (scripts/fake_idp.py), hub-api with HUB_AUTH=oidc serving the built hub, and a browser doing Authorization Code
# with PKCE. Proves what the bank's provider will meet: discovery, JWKS, RS256 verification, the identity map,
# what each person may then do, silent renew, sign-out, and the refusals. Needs the hub built (hub/dist), Node with
# playwright-core (hub/node_modules) and a Chromium (CHROMIUM_PATH or Playwright's registered one).
#   scripts/smoke-oidc.sh
set -eu
cd "$(dirname "$0")/.."
IDP_PORT="${IDP_PORT:-9443}"; HUB_PORT="${HUB_PORT:-18443}"
for port in "$IDP_PORT" "$HUB_PORT"; do python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) else 1)" "$port" || { echo "port $port is in use"; exit 1; }; done
work="$(mktemp -d)"; idp=""; hub=""
trap 'kill $idp $hub 2>/dev/null || true; rm -rf "$work"' EXIT
# A throwaway certificate for the provider; hub-api trusts it through SSL_CERT_FILE for this run only.
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$work/key.pem" -out "$work/cert.pem" -days 1 -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1" >/dev/null 2>&1
IDP_LOG=1 exec python3 scripts/fake_idp.py --port "$IDP_PORT" --cert "$work/cert.pem" --key "$work/key.pem" --audience hub-api --client hub-web > "$work/idp.log" 2>&1 &
idp=$!
sleep 1
root="$PWD"
hubenv() { exec env SSL_CERT_FILE="$work/cert.pem" HUB_ENV=sandbox HUB_AUTH=oidc HUB_IDP_ISSUER="https://127.0.0.1:$IDP_PORT" HUB_IDP_AUDIENCE=hub-api \
  HUB_AI_SECURITY_GROUP=GROUP_ID_AI_SECURITY HUB_OWNER_DOMAIN=bank.example HUB_WEB_OIDC_AUTHORITY="https://127.0.0.1:$IDP_PORT" HUB_WEB_OIDC_CLIENT_ID=hub-web \
  HUB_WEB_OIDC_SCOPE="openid profile email hub-api" HUB_PUBLIC_URL="http://127.0.0.1:$HUB_PORT" HUB_LISTEN_PORT="$HUB_PORT" HUB_STATIC_DIR="$root/hub/dist" \
  HUB_DB=:memory: "$@"; }
(cd services/hub-api && hubenv python3 -m hubapi check-config)
(cd services/hub-api && hubenv python3 -m hubapi serve > "$work/hub.log" 2>&1) &
hub=$!
sleep 2
python3 - "$HUB_PORT" <<'PY'
import json, sys, urllib.request
r = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/api/ready", timeout=5).read()); assert r["status"] == "ready" and r["checks"]["identity"] == "ok", r
print("hub-api ready with the provider's keys:", r["checks"])
PY
(cd hub && HUB_BASE="http://127.0.0.1:$HUB_PORT" IDP_BASE="https://127.0.0.1:$IDP_PORT" NODE_PATH="$PWD/node_modules" node tools/oidctest.cjs) || { echo "--- hub-api log"; tail -20 "$work/hub.log"; echo "--- idp log"; tail -40 "$work/idp.log"; exit 1; }
