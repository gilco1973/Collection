"""Request models and admission rules for starting and rolling back audits."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from kb_librarian.agent.prompts import CAPABILITY_PROMPTS
from kb_librarian.api.deps import AppState


class StartAudit(BaseModel):
    type: str = Field(default="agent", pattern="^(agent|offline)$")
    dry_run: bool = True
    capabilities: list[str] | None = Field(default=None, min_length=1)  # [] would silently run the defaults
    max_turns: int | None = Field(default=None, ge=1, le=200)
    max_budget_usd: float | None = Field(default=None, gt=0)
    network: bool = False
    reason: str | None = Field(default=None, max_length=500)


class RollbackBody(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    force: bool = False


def spent_today(state: AppState) -> float:
    """Cost already saved today plus the budgets reserved by audits still running."""
    today = datetime.now(UTC).date()
    saved = sum(e.summary["total_cost_usd"] for e in state.store.entries() if e.audit_date.date() == today)
    return saved + sum(state.reserved_budgets.values())


def validate(body: StartAudit, state: AppState) -> float:
    """Reject unknown capabilities, over-ceiling budgets, a concurrent run and a busted daily cap.

    Must run under ``state.admission`` so two requests cannot both pass before either registers.
    """
    unknown = sorted(set(body.capabilities or []) - set(CAPABILITY_PROMPTS))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown capabilities: {unknown}")
    if body.max_budget_usd is not None and body.max_budget_usd > state.settings.max_budget_usd:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"max_budget_usd exceeds the server ceiling {state.settings.max_budget_usd}",
        )
    if state.manager.running() or state.reserved_budgets:
        running = (state.manager.running() or list(state.reserved_budgets))[0]
        raise HTTPException(status.HTTP_409_CONFLICT, f"an audit is already running: {running}")
    budget = body.max_budget_usd or state.settings.max_budget_usd
    if body.type == "agent" and spent_today(state) + budget > state.settings.daily_budget_usd:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "daily budget ceiling reached (KB_DAILY_BUDGET_USD)")
    return budget
