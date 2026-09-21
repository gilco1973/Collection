#!/bin/sh
# The delivery zip: the release bundle's tree (source, the prebuilt hub, deploy files, documentation) at the top,
# with deliverables/ (the three PDFs, the walkthrough video, the teaching guide, the screenshots) beside it, a
# DELIVERY.txt, and one MANIFEST.sha256 over every file in the zip. INSTALL.md and HANDOVER.md are at the top
# because the repository keeps them there.
#   scripts/package.sh [output dir]      -> release/collection-<sha>.zip and .sha256
# The bundle's own gates run first (shelf, vendoring); the zip is unpacked again and its manifest checked before
# the script reports success, so a delivery that would fail §0 of INSTALL.md is never written.
set -eu
cd "$(dirname "$0")/.."
out="${1:-release}"
mkdir -p "$out"
out="$(cd "$out" && pwd)"          # absolute from here on: the script changes directory below
sha="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
name="collection-$sha"
work="$(mktemp -d)"; check=""
trap 'rm -rf "$work" "$check"' EXIT
scripts/bundle.sh "$work/bundle" >/dev/null
top="$work/zip/$name"
mkdir -p "$top" "$top/deliverables/screenshots"
tar -C "$top" --strip-components=1 -xzf "$work/bundle/$name.tar.gz"     # the repository is the top of the zip
cp INSTALL.md HANDOVER.md "$top/"
cp docs/pdf/user-manual.pdf docs/pdf/technical-guide.pdf docs/pdf/leadership-brief.pdf docs/teaching/teaching-the-collection.html "$top/deliverables/"
for f in demo/out/collection-walkthrough.mp4 demo/out/collection-walkthrough.en.vtt; do
  [ -f "$f" ] && cp "$f" "$top/deliverables/" || echo "note: $f is not built; the zip ships without it (demo/README.md says how to build it)"
done
for f in docs/pdf/img/*.png; do cp "$f" "$top/deliverables/screenshots/"; done
[ -d demo/shots ] && cp demo/shots/*.png "$top/deliverables/screenshots/" 2>/dev/null || true
printf '%s\n' "collection $sha, packaged $(date -u +%Y-%m-%dT%H:%M:%SZ)" "" \
  "Start with INSTALL.md. The repository is this directory (scripts/, services/, hub/ ...); the PDFs, the video, the teaching guide and the screenshots are in deliverables/." \
  "MANIFEST.sha256 covers every file here, deliverables included: sha256sum -c --quiet MANIFEST.sha256" > "$top/DELIVERY.txt"
# One manifest over everything in the zip (the bundle's own manifest covered only the repository tree; this one replaces it).
(cd "$top" && find . -type f ! -name MANIFEST.sha256 -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > MANIFEST.sha256)
rm -f "$out/$name.zip"
(cd "$work/zip" && python3 -c "
import os, sys, zipfile
name, dest = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(name):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f); z.write(p, p)
" "$name" "$out/$name.zip")
(cd "$out" && sha256sum "$name.zip" > "$name.zip.sha256")
# Prove the delivery: unpack the zip somewhere clean and check every file against the manifest, as INSTALL.md §0 does.
check="$(mktemp -d)"
(cd "$check" && unzip -q "$out/$name.zip" && cd "$name" && sha256sum -c --quiet MANIFEST.sha256)
printf 'wrote %s/%s.zip (%s) and its .sha256; manifest verified from a clean unpack\n' "$out" "$name" "$(du -h "$out/$name.zip" | cut -f1)"
