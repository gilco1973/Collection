#!/bin/sh
# The delivery zip: the release bundle's tree (source, the prebuilt hub, deploy files, documentation, MANIFEST),
# the three PDFs, the walkthrough video and the screenshots, with INSTALL.md and HANDOVER.md at the top.
#   scripts/package.sh [output dir]      -> release/collection-<sha>.zip and .sha256
# The bundle's own gates run first (shelf, vendoring); the zip is unpacked again and its manifest checked before
# the script reports success, so a delivery that would fail §0 of INSTALL.md is never written.
set -eu
cd "$(dirname "$0")/.."
out="${1:-release}"
sha="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
name="collection-$sha"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
scripts/bundle.sh "$work/bundle" >/dev/null
mkdir -p "$work/zip/$name" "$work/zip/$name/deliverables/screenshots"
tar -C "$work/zip/$name" -xzf "$work/bundle/$name.tar.gz"
cp INSTALL.md HANDOVER.md "$work/zip/$name/"
cp docs/pdf/user-manual.pdf docs/pdf/technical-guide.pdf docs/pdf/leadership-brief.pdf "$work/zip/$name/deliverables/"
for f in demo/out/collection-walkthrough.mp4 demo/out/collection-walkthrough.en.vtt; do
  [ -f "$f" ] && cp "$f" "$work/zip/$name/deliverables/" || echo "note: $f is not built; the zip ships without it (demo/README.md says how to build it)"
done
for f in docs/pdf/img/*.png; do cp "$f" "$work/zip/$name/deliverables/screenshots/"; done
[ -d demo/shots ] && cp demo/shots/*.png "$work/zip/$name/deliverables/screenshots/" 2>/dev/null || true
printf '%s\n' "collection $sha, packaged $(date -u +%Y-%m-%dT%H:%M:%SZ)" "" "Start with INSTALL.md. The repository is in $name/ with MANIFEST.sha256; the PDFs, the video and the screenshots are in deliverables/." > "$work/zip/$name/DELIVERY.txt"
mkdir -p "$out"
(cd "$work/zip" && rm -f "$OLDPWD/$out/$name.zip" && python3 -c "
import os, sys, zipfile
name, dest = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(name):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f); z.write(p, p)
" "$name" "$OLDPWD/$out/$name.zip")
(cd "$out" && sha256sum "$name.zip" > "$name.zip.sha256")
# Prove the delivery: unpack the zip somewhere clean and check every file against the manifest.
check="$(mktemp -d)"
(cd "$check" && unzip -q "$OLDPWD/$out/$name.zip" && cd "$name/$name" && sha256sum -c --quiet MANIFEST.sha256) && rm -rf "$check"
printf 'wrote %s/%s.zip (%s) and its .sha256; manifest verified from a clean unpack\n' "$out" "$name" "$(du -h "$out/$name.zip" | cut -f1)"
