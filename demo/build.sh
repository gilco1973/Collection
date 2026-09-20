#!/usr/bin/env bash
# Build the walkthrough video end to end. Run from the repository root with the hub preview on :4173 and the
# knowledge-base console on :8765 (see README.md). Outputs land under demo/out/.
set -euo pipefail
cd "$(dirname "$0")"
SKILL=../components/skills/walkthrough-video
export NODE_PATH="${NODE_PATH:-$PWD/../hub/node_modules}"
mkdir -p build
( cd ../components/python/governed-action-loop && python3 example.py ) > build/term-example.txt
( cd .. && python3 tools/catalog.py --test --only python 2>&1 | grep -E "^(==|!!|ok|FAILED)" ) > build/term-tests.txt
( cd .. && python3 tools/catalog.py --list ) > build/term-list.txt
( cd .. && python3 tools/catalog.py --write && python3 tools/catalog.py --check ) > build/term-check.txt
node capture_shots.cjs
python3 $SKILL/deck.py slides.py
node $SKILL/build_frames.cjs
python3 $SKILL/build_narration.py --provider "${NARRATION:-captions}"
WALKTHROUGH_OUT=out/collection-walkthrough.mp4 python3 $SKILL/build_video.py
