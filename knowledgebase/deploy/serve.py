"""Serve the API and the built console from one process (container entry point)."""

import os
import sys
from pathlib import Path

import uvicorn
from pydantic import ValidationError

from kb_librarian.api.app import create_app
from kb_librarian.api.static import mount_console
from kb_librarian.config import settings_errors

ROOT = Path(os.environ.get("KB_ROOT", "/srv/knowledge-base"))
# uvicorn reads FORWARDED_ALLOW_IPS itself: set it to the ingress address so request.client.host is
# the real client (the problem-report throttle keys on it) and X-Forwarded-For from anyone else is ignored.
try:
    app = create_app(ROOT, cors_origins=[o for o in os.environ.get("KB_API_CORS_ORIGINS", "").split(",") if o])
except ValidationError as exc:  # a rejected setting is one diagnostic line per variable, never a traceback
    for line in settings_errors(exc):
        print(f"FAIL settings — {line}", file=sys.stderr)
    sys.exit(2)
mount_console(app, ROOT / "web" / "dist")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.environ.get("KB_API_HOST", "0.0.0.0"),
        port=int(os.environ.get("KB_API_PORT", "8765")),
        log_config=None,  # uvicorn's own lines go through the root logger create_app configured (JSON by default)
        access_log=False,  # the API's RequestLog middleware writes the one access line per request
    )
