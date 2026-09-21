#!/bin/sh
# The pixel guard (every screen against its artboard, 0 px) and the browser flows (navigation, intake, discover,
# assistant, settings) on the production build, served by vite preview on a port of its own. Needs hub/dist, Node with
# playwright-core (hub/node_modules) and a Chromium (CHROMIUM_PATH or Playwright's registered one).
#   scripts/smoke-hub-browser.sh
set -eu
cd "$(dirname "$0")/../hub"
PORT="${HUB_PREVIEW_PORT:-4179}"
python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) else 1)" "$PORT" || { echo "port $PORT is in use"; exit 1; }
[ -f dist/index.html ] || { echo "hub/dist is missing: run pnpm build first"; exit 1; }
preview=""
trap 'kill $preview 2>/dev/null || true' EXIT
pnpm exec vite preview --port "$PORT" --strictPort > /dev/null 2>&1 &
preview=$!
for i in $(seq 1 50); do python3 -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) else 0)" "$PORT" && break; sleep 0.2; done
export HUB_BASE="http://127.0.0.1:$PORT"
node tools/shoot.cjs > /dev/null
python3 tools/diff.py
pnpm run --silent verify:e2e > /dev/null
echo "ok: pixel guard at 0 px and every browser flow passed"
