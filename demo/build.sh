#!/usr/bin/env bash
# Build the walkthrough video end to end. Run from demo/ with the hub preview on :4173 and the knowledge-base
# console on :8765 (see README.md). Outputs land under demo/out/.
set -euo pipefail
cd "$(dirname "$0")"
SKILL=../components/skills/walkthrough-video
export NODE_PATH="${NODE_PATH:-$PWD/../hub/node_modules}"
mkdir -p build shots
( cd ../components/agents/incident-first-read-agent && python3 example.py ) > build/term-agent.txt
( cd ../components/agents/incident-first-read-agent && python3 example_mcp.py ) > build/term-mcp.txt
# --list prints fixed columns: category, language, status, version, stage, sign-off, name (columns 101-128), summary; keep everything through the name.
( cd .. && python3 tools/shelf.py --list | cut -c1-128 | head -32 ) > build/term-list.txt
( cd ../services/hub-api && HUB_ENV=production HUB_AUTH=mock HUB_ASSISTANT=fake python3 -m hubapi check-config || true ) > build/term-checkconfig.txt
( cd .. && scripts/verify.sh python 2>&1 | grep -E "^==|^ok:" ) > build/term-verify.txt
( cd .. && rm -rf release && scripts/bundle.sh && rm -rf /tmp/clean && mkdir -p /tmp/clean && tar -xzf release/collection-*.tar.gz -C /tmp/clean && cd /tmp/clean/collection-* && sha256sum -c MANIFEST.sha256 --quiet && echo "MANIFEST.sha256: every file verified" && scripts/verify.sh python 2>&1 | grep -E "^==|^ok:" | tail -6 ) > build/term-bundle.txt
python3 ../docs/pdf/diagrams.py --svg build >/dev/null
rm -f shots/*.png
node capture_shots.cjs
python3 $SKILL/deck.py slides.py
node $SKILL/build_frames.cjs
python3 $SKILL/build_narration.py --provider "${NARRATION:-captions}"
WALKTHROUGH_OUT=out/collection-walkthrough.mp4 python3 $SKILL/build_video.py
