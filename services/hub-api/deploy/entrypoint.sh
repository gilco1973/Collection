#!/bin/sh
# Fail closed: the configuration is checked before the service listens; a live process with a missing gate never starts.
set -eu
cd "$(dirname "$0")"   # /app in the image; wherever the tree is assembled otherwise
python3 -m hubapi check-config
exec python3 -m hubapi serve
