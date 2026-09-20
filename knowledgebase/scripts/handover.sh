#!/usr/bin/env bash
# Build a versioned handover package: KnowledgeBase-handover-v<version>.zip containing every
# tracked file of this directory at HEAD plus HANDOVER.md (the handover document) and a manifest.
#
# Rule: a handover zip is never produced without a version and a handover document. The version
# must already be recorded in HANDOVER.md (its "Handover history" table) so the zip and the doc
# cannot disagree; the script refuses otherwise.
#
# Usage: scripts/handover.sh <version> [output-dir]     e.g. scripts/handover.sh 2 /tmp/out
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
version="${1:?usage: scripts/handover.sh <version> [output-dir]}"
out="${2:-$ROOT/..}"
doc="HANDOVER.md"
[ -f "$doc" ] || { echo "MISSING: $doc — write the handover document first"; exit 1; }
grep -Eq "^\| *v${version} *\|" "$doc" || { echo "HANDOVER.md has no history row for v${version}; add it first"; exit 1; }
if [ -n "$(git status --porcelain -- . )" ]; then
  echo "working tree is not clean; commit first so the package matches a commit"; exit 1
fi
commit="$(git rev-parse --short=12 HEAD)"
stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
name="KnowledgeBase-handover-v${version}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/KnowledgeBase"
# Tracked files only (no .venv, node_modules, dist, .librarian, caches): the package equals the commit.
git ls-files -z -- . | tar --null -T - -cf - | tar -C "$work/KnowledgeBase" -xf -
count="$(git ls-files -- . | wc -l | tr -d ' ')"
{
  echo "package: $name"
  echo "version: v$version"
  echo "commit: $commit"
  echo "built: $stamp"
  echo "files: $count"
  echo "document: KnowledgeBase/HANDOVER.md"
} > "$work/MANIFEST.txt"
cp "$doc" "$work/HANDOVER.md"
mkdir -p "$out"
rm -f "$out/$name.zip"
(cd "$work" && zip -qr "$out/$name.zip" KnowledgeBase HANDOVER.md MANIFEST.txt)
echo "built $out/$name.zip (v$version, commit $commit, $count files)"
