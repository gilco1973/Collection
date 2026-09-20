"""Operator endpoints for the insights file: read what the last run wrote, or regenerate it now."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from kb_librarian.api import service
from kb_librarian.api.deps import AppState, get_state, require_operator, same_origin
from kb_librarian.insights import store
from kb_librarian.insights.collect import DEFAULT_WINDOW_DAYS, collect
from kb_librarian.insights.models import Insights

router = APIRouter()
NO_INSIGHTS = "no insights yet; run `kb-librarian insights` or refresh them from the console"


def _without_withheld(state: AppState, insights: Insights) -> Insights:
    """The file minus any page withheld *now*: a page flagged after the last run is not served either."""
    withheld = service.withheld_paths(state.catalog(), state.store.latest_completed())
    pages = {path: page for path, page in insights.pages.items() if path not in withheld}
    return insights.model_copy(update={"pages": pages})


def _regenerate(state: AppState) -> Insights:
    catalog = state.catalog()
    withheld = service.withheld_paths(catalog, state.store.latest_completed())
    insights = collect(
        state.root,
        state.config,
        catalog,
        withheld,
        k=state.settings.insights_k,
        window_days=DEFAULT_WINDOW_DAYS,
        now=datetime.now(UTC),
    )
    store.write(state.root, insights)
    return insights


@router.get("/insights", dependencies=[Depends(require_operator)])
def get_insights(state: AppState = Depends(get_state)) -> dict:
    """The stored aggregates (`.librarian/insights/latest.json`); 404 with a fixed message until generated."""
    stored = store.read(state.root)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_INSIGHTS)
    return _without_withheld(state, stored).model_dump(mode="json")


@router.post("/insights/refresh", dependencies=[Depends(require_operator), Depends(same_origin)])
async def refresh_insights(state: AppState = Depends(get_state)) -> dict:
    """Regenerate on the threadpool (every record and problem file is read) and return the result."""
    insights = await run_in_threadpool(_regenerate, state)
    return insights.model_dump(mode="json")
