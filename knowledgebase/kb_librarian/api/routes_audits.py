"""Operator endpoints: start, inspect, cancel and roll back audits."""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from kb_librarian.actions import ActionLog
from kb_librarian.agent.runner import run_agent_audit, run_offline_audit
from kb_librarian.api.admission import RollbackBody, StartAudit, validate
from kb_librarian.api.deps import AppState, Principal, get_state, require_operator
from kb_librarian.models import AuditReport
from kb_librarian.reports import report_summary
from kb_librarian.tools.context import SNAPSHOTS_DIR

router = APIRouter()
log = logging.getLogger(__name__)
TERMINAL = ("completed", "failed", "cancelled")
_START_TIMEOUT_S = 30


@router.get("/audits")
def list_audits(
    mode: str | None = Query(default=None, pattern="^(dry|live)$"),
    status_: str | None = Query(default=None, alias="status"),
    type_: str | None = Query(default=None, alias="type"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    state: AppState = Depends(get_state),
) -> dict:
    entries = state.store.entries()  # the index carries every summary; no report is loaded here
    if status_:
        entries = [e for e in entries if e.status == status_]
    if mode:
        entries = [e for e in entries if e.dry_run == (mode == "dry")]
    if type_:
        entries = [e for e in entries if e.audit_type == type_]
    start = (page - 1) * page_size
    return {"items": [e.summary for e in entries[start : start + page_size]], "total": len(entries)}


async def _launch_agent(
    body: StartAudit, state: AppState, dry_run: bool, requested_by: str | None, budget: float
) -> str:
    loop = asyncio.get_running_loop()
    registered: asyncio.Future[str] = loop.create_future()
    slot = f"starting-{id(registered)}"
    state.reserved_budgets[slot] = budget  # counts against admission until the run registers

    def on_registered(audit_id: str) -> None:
        if not registered.done():
            registered.set_result(audit_id)

    task = asyncio.create_task(
        run_agent_audit(
            state.settings,
            state.root,
            dry_run=dry_run,
            capabilities=body.capabilities,
            offline=not body.network,
            max_turns=body.max_turns,
            max_budget_usd=body.max_budget_usd,
            manager=state.manager,
            reason=body.reason,
            requested_by=requested_by,  # "key" for the shared key, "user:<16 hex>" (a pseudonym) for a person
            on_registered=on_registered,
        )
    )
    try:
        done, _ = await asyncio.wait({task, registered}, timeout=_START_TIMEOUT_S, return_when=asyncio.FIRST_COMPLETED)
    finally:
        state.reserved_budgets.pop(slot, None)
    if registered.done():
        audit_id = registered.result()
        state.tasks[audit_id] = task
        state.reserved_budgets[audit_id] = budget
        task.add_done_callback(lambda _t: (state.tasks.pop(audit_id, None), state.reserved_budgets.pop(audit_id, None)))
        return audit_id
    if task in done and not task.cancelled() and task.exception():
        log.error("audit could not start", exc_info=task.exception())
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "audit could not start; see the server log")
    task.cancel()
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "audit did not start within the timeout")


def _attribute(audit_id: str, principal: Principal) -> None:
    """The report carries a pseudonym (``requested_by``); the server log, which only operators read,
    carries the subject, so an audit can be traced to a person without the report exposing one."""
    subject = principal.user.sub if principal.via == "group" and principal.user else None
    log.info("audit %s requested by %s (subject %s)", audit_id, principal.requested_by, subject)


@router.post("/audits", status_code=status.HTTP_202_ACCEPTED)
async def start_audit(
    body: StartAudit, state: AppState = Depends(get_state), principal: Principal = Depends(require_operator)
) -> dict:
    dry_run = state.settings.resolve_dry_run(body.dry_run)
    if not dry_run and not (body.reason or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a reason is required for a live audit")
    forced = dry_run and not body.dry_run
    async with state.admission:  # single-flight: nobody else validates until this run holds its slot
        budget = validate(body, state)
        if body.type == "offline":
            slot = f"offline-{id(body)}"
            state.reserved_budgets[slot] = 0.0  # admits nothing else while the offline run is in flight
        else:
            audit_id = await _launch_agent(body, state, dry_run, principal.requested_by, budget)
            _attribute(audit_id, principal)
            return {"audit_id": audit_id, "dry_run": dry_run, "forced_dry_run": forced}
    try:
        report = await asyncio.to_thread(
            run_offline_audit,
            state.settings,
            state.root,
            dry_run=dry_run,
            offline=not body.network,
            requested_by=principal.requested_by,
        )
    finally:
        state.reserved_budgets.pop(slot, None)
    _attribute(report.audit_id, principal)
    return {"audit_id": report.audit_id, "dry_run": report.dry_run, "forced_dry_run": forced}


@router.get("/audits/{audit_id}")
def get_audit(audit_id: str, state: AppState = Depends(get_state)) -> dict:
    report = _load(state, audit_id)
    return {**report.model_dump(mode="json"), "summary": report_summary(report)}


@router.post(
    "/audits/{audit_id}/cancel", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_operator)]
)
async def cancel_audit(audit_id: str, state: AppState = Depends(get_state)) -> dict:
    report = _load(state, audit_id)
    if report.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, f"audit is {report.status}")
    state.manager.cancel(audit_id)  # the marker reaches a runner in another process (CLI) at its next tool call
    task = state.tasks.get(audit_id)
    if task is None and audit_id not in state.manager.running():
        # Nothing in this process owns the run: record the cancel so the console stops waiting; a foreign
        # runner that is still alive will overwrite this with its own final status.
        report.finish("failed", error="cancelled by an operator: no process in the API was running this audit")
        state.store.save(report)
        return {"status": "failed"}
    if task is not None and not task.done():
        task.cancel()  # the runner maps CancelledError to a persisted `cancelled` report
    return {"status": "cancelling"}


@router.post("/audits/{audit_id}/actions/{action_id}/rollback", dependencies=[Depends(require_operator)])
async def rollback(audit_id: str, action_id: str, body: RollbackBody, state: AppState = Depends(get_state)) -> dict:
    async with state.lock_for(audit_id):
        report = _load(state, audit_id)
        if report.status not in TERMINAL:
            raise HTTPException(status.HTTP_409_CONFLICT, f"audit is {report.status}; roll back after it finishes")
        log_ = ActionLog(state.root / state.config.docs_root, report, state.root / SNAPSHOTS_DIR)
        try:
            action = log_.rollback(action_id, body.reason, force=body.force)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc).strip('"')) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        state.store.save(report)
    return {"action": action.model_dump(mode="json")}


@router.get("/audits/{audit_id}/export")
def export(
    audit_id: str, format: str = Query(default="md", pattern="^(json|md)$"), state: AppState = Depends(get_state)
):
    _load(state, audit_id)
    path: Path = state.store.reports_dir / f"{audit_id}.{format}"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no {format} export for '{audit_id}'")
    return FileResponse(
        path, filename=path.name, media_type="application/json" if format == "json" else "text/markdown"
    )


def _load(state: AppState, audit_id: str) -> AuditReport:
    try:
        return state.store.load(audit_id)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no report '{audit_id}'") from exc
