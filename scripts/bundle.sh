#!/bin/sh
# An offline release: everything the bank's build needs, with nothing to fetch on its side.
#   scripts/bundle.sh [output dir]      -> release/collection-<sha>.tar.gz and .sha256
# Inside: the components, the tools, the services, the hub's source and its built dist/ (built here with the
# sandbox env; the bank rebuilds with hub/.env.production if it changes the identity provider), the deploy files,
# the documentation, and a MANIFEST with every file's sha256. No node_modules, no caches, no secrets.
set -eu
cd "$(dirname "$0")/.."
out="${1:-release}"
sha="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
name="collection-$sha"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$out" "$work/$name"
python3 tools/shelf.py --check >/dev/null
python3 services/vendor.py --check >/dev/null
if [ ! -d hub/dist ] || [ -z "$(ls -A hub/dist 2>/dev/null)" ]; then
  (cd hub && pnpm install --frozen-lockfile --prefer-offline >/dev/null && pnpm build >/dev/null)
fi
git ls-files -z | grep -zv '^demo/\|^\.github/' | xargs -0 -I{} sh -c 'mkdir -p "$1/$(dirname "$2")" && cp "$2" "$1/$2"' _ "$work/$name" {}
mkdir -p "$work/$name/hub/dist" && cp -r hub/dist/. "$work/$name/hub/dist/"
find "$work/$name" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
(cd "$work/$name" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256)
printf '%s\n' "collection $sha, built $(date -u +%Y-%m-%dT%H:%M:%SZ)" "" "Unpack, then: scripts/verify.sh python (no network, no Node needed); the hub is prebuilt in hub/dist." "Rebuild the hub only if hub/.env.production changes: cd hub && pnpm install --offline && pnpm build (a pnpm store is needed for that)." "Images: services/*/deploy/Dockerfile from this directory as the build context." > "$work/$name/RELEASE.txt"
tar -C "$work" -czf "$out/$name.tar.gz" "$name"
(cd "$out" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256")
printf 'wrote %s/%s.tar.gz (%s) and its .sha256\n' "$out" "$name" "$(du -h "$out/$name.tar.gz" | cut -f1)"
