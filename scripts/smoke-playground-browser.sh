#!/bin/sh
# The AI Playground's page in a real browser: a fresh data directory, the server on a port of its own, then
# playground/tools/uitest.cjs (solutions, try it, a blocked and a clear run, triage refused to the tester, compare,
# phone width, no page errors, answers shown as text). Needs Node with playwright-core (hub/node_modules) and Chromium.
#   scripts/smoke-playground-browser.sh [screenshot dir]
set -eu
cd "$(dirname "$0")/../playground"
PORT="${PLAYGROUND_PORT:-8779}"
python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) else 1)" "$PORT" || { echo "port $PORT is in use"; exit 1; }
data="$(mktemp -d)"; server=""
trap 'kill $server 2>/dev/null || true; rm -rf "$data"' EXIT
token="smoke-$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
python3 -c "
import sys
from aiplayground import server
server.make_server(sys.argv[1], port=int(sys.argv[2]), token=sys.argv[3], quiet=True).serve_forever()" "$data" "$PORT" "$token" &
server=$!
for i in $(seq 1 50); do python3 -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) else 0)" "$PORT" && break; sleep 0.2; done
PLAYGROUND_URL="http://127.0.0.1:$PORT" PLAYGROUND_TOKEN="$token" node tools/uitest.cjs ${1:+"$1"}
