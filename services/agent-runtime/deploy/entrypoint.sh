#!/bin/sh
# Fail closed: the configuration is checked before the runtime listens; `verify-record` walks the chain on every start.
set -eu
cd "$(dirname "$0")"   # /app in the image; wherever the tree is assembled otherwise
python3 -m agentrt check-config
python3 -m agentrt verify-record
exec python3 -m agentrt serve
