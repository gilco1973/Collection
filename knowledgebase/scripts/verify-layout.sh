#!/usr/bin/env bash
# Verifies the project layout contract: required files and sections, file-size limit,
# and that the content is organisation-neutral. Exit 0 on success.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fail=0
need() { [ -e "$1" ] || { echo "MISSING: $1"; fail=1; }; }

for f in README.md CLAUDE.md pyproject.toml kb.config.yaml docs/index.md \
         docs/integrations/atlassian.md docs/skills/templates/SKILL-template.md \
         docs/videos/catalog.yaml docs/resources/catalog.yaml; do need "$f"; done
for s in onboarding paved-roads best-practices skills videos tutorials wiki integrations resources governance; do
  need "docs/$s/README.md"
done

long=$(find . \( -path ./.venv -o -path ./.librarian -o -path ./.pytest_cache -o -path ./.ruff_cache -o -path ./web/node_modules -o -path ./web/dist -o -path ./design \) -prune -o -type f \( -name '*.py' -o -name '*.md' -o -name '*.ts' -o -name '*.tsx' \) -print | xargs wc -l | awk '$1>200 && $2!="total"')
if [ -n "$long" ]; then echo "FILES OVER 200 LINES:"; echo "$long"; fail=1; fi

# Organisation-neutral content: none of these product names may appear anywhere.
banned="olor""in|bay""it|claud""ette"
scan() {
  grep -rniIE "$banned" --exclude-dir=.venv --exclude-dir=.git --exclude-dir=__pycache__ \
    --exclude-dir=.ruff_cache --exclude-dir=.pytest_cache --exclude-dir=.librarian \
    --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=coverage \
    --exclude=verify-layout.sh --exclude=poetry.lock .
}
if scan >/dev/null; then
  echo "PROPRIETARY REFERENCES FOUND:"; scan | head; fail=1
fi

[ "$fail" -eq 0 ] && echo "layout ok"
exit "$fail"
