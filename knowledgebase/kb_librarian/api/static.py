"""Serve the built console next to the API with a single-page-app fallback."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_console(app: FastAPI, dist: Path) -> bool:
    """Mount ``dist`` (a Vite build) so deep links and refreshes resolve to ``index.html``.

    Returns False when there is no build to serve. Must be called after the API
    router is included so ``/api/*`` keeps precedence over the fallback.
    """
    index = dist / "index.html"
    if not index.is_file():
        return False
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="console-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def console(path: str, request: Request) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "not found")
        candidate = (dist / path).resolve() if path else index
        if path and dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return True
