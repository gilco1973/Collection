#!/bin/sh
# The container trees without a container daemon: assemble exactly what each Dockerfile COPYs into a clean
# directory, run the fail-closed entrypoint in the sandbox, hit /health, stop. Proves the COPY set is complete and
# the entrypoints work; the images themselves are built by the bank's pipeline from the same Dockerfiles.
set -eu
cd "$(dirname "$0")/.."
root="$(mktemp -d)"; trap 'rm -rf "$root"; kill $(jobs -p) 2>/dev/null || true' EXIT
[ -d hub/dist ] || (cd hub && pnpm build >/dev/null)

# hub: services/hub-api/deploy/Dockerfile
h="$root/hub"; mkdir -p "$h/app" "$h/var"
cp -r services/hub-api/hubapi "$h/app/hubapi"; cp -r services/hub-api/data "$h/app/data"; cp services/hub-api/deploy/entrypoint.sh "$h/app/entrypoint.sh"; cp -r hub/dist "$h/app/hub-dist"
python3 -m compileall -q "$h/app/hubapi"
(cd "$h/app" && HUB_ENV=sandbox HUB_AUTH=mock HUB_ASSISTANT=fake HUB_SECRETS=env HUB_DB="$h/var/hub.db" HUB_STATIC_DIR="$h/app/hub-dist" HUB_LISTEN_PORT=18080 \
  HUB_IDENTITY_MAP="$h/app/data/identity-map.example.json" HUB_CONSUMERS_FILE="$h/app/data/consumers.example.json" HUB_COLLECTION_FILE="$h/app/data/collection.json" \
  sh ./entrypoint.sh > "$root/hub.log" 2>&1 &)
sleep 2
python3 - <<'PY'
import json, urllib.request
h = json.loads(urllib.request.urlopen("http://127.0.0.1:18080/api/health", timeout=3).read()); assert h["status"] == "ok" and h["record"] == "file", h
page = urllib.request.urlopen("http://127.0.0.1:18080/discover", timeout=3).read().decode(); assert "/config.js" in page and "<title>" in page
cfg = urllib.request.urlopen("http://127.0.0.1:18080/config.js", timeout=3).read().decode(); assert '"VITE_API_MODE": "http"' in cfg
print("hub tree: health ok, page served, config.js served")
PY
# production must refuse this tree's fakes
if (cd "$h/app" && HUB_ENV=production HUB_AUTH=mock python3 -m hubapi check-config >/dev/null 2>&1); then echo "hub: production accepted mock identity"; exit 1; fi
echo "hub tree: production refuses fakes"

# agent: services/agent-runtime/deploy/Dockerfile
a="$root/agent"; mkdir -p "$a/app" "$a/var"
cp -r services/agent-runtime/agentrt "$a/app/agentrt"; cp services/agent-runtime/deploy/entrypoint.sh "$a/app/entrypoint.sh"
python3 -m compileall -q "$a/app/agentrt"
(cd "$a/app" && AGENT_ENV=sandbox AGENT_IDENTITY=fake AGENT_SIGNING=local AGENT_ENGINE=rules AGENT_SECRETS=env AGENT_DB="$a/var/record.db" AGENT_LISTEN_PORT=18081 AGENT_PUBLIC_URL=http://localhost:18081/mcp \
  sh ./entrypoint.sh > "$root/agent.log" 2>&1 &)
sleep 2
python3 - <<'PY'
import json, urllib.request
h = json.loads(urllib.request.urlopen("http://127.0.0.1:18081/health", timeout=3).read()); assert h["status"] == "ok" and h["engine"] == "rules", h
print("agent tree: health ok, record verified at start")
PY
if (cd "$a/app" && AGENT_ENV=production python3 -m agentrt check-config >/dev/null 2>&1); then echo "agent: production accepted fakes"; exit 1; fi
echo "agent tree: production refuses fakes"
pkill -f "hubapi serve" >/dev/null 2>&1 || true; pkill -f "agentrt serve" >/dev/null 2>&1 || true
echo "ok: both container trees start, answer, and refuse fakes in production"
