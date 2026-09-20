"""The librarian chat endpoint. Open to any role, same as search: nothing it can do mutates state."""

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from kb_librarian.api import service
from kb_librarian.api.deps import AppState, current_user, get_state
from kb_librarian.auth.session import User
from kb_librarian.chat import telemetry
from kb_librarian.chat.prompts import ChatContext, ChatTurn
from kb_librarian.chat.runner import ChatAnswer, run_chat
from kb_librarian.chat.spend import ledger_for

log = logging.getLogger(__name__)
router = APIRouter()
_WINDOW_S, _MESSAGES_PER_WINDOW = 60.0, 10
BUDGET_SPENT = "the librarian's daily chat budget is spent; try again tomorrow"
_recent: dict[str, deque[float]] = defaultdict(deque)
_throttle_lock = threading.Lock()  # the route runs on threadpool workers


class ChatTurnBody(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatContextBody(BaseModel):
    """The page the reader is on and, optionally, the text they selected on it. ``title`` is what
    the console shows in its context chip; it is size-checked but never used — the prompt takes
    the catalog's title, so no client text lands in the prompt outside the selection envelope."""

    path: str = Field(min_length=1, max_length=400)
    title: str = Field(default="", max_length=200)
    selection: str = Field(default="", max_length=2000)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurnBody] = Field(default_factory=list, max_length=16)
    lang: str | None = Field(default=None, max_length=8, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,4})?$")  # a language tag
    mode: Literal["ask", "explain", "elaborate", "quiz"] = "ask"
    context: ChatContextBody | None = None

    @model_validator(mode="after")
    def _actions_need_a_page(self) -> "ChatBody":
        if self.mode != "ask" and self.context is None:
            raise ValueError(f"mode '{self.mode}' needs a context page")
        return self


def _throttle(client: str) -> None:
    now = time.monotonic()
    with _throttle_lock:
        idle = [k for k, w in _recent.items() if k != client and (not w or now - w[-1] > _WINDOW_S)]
        for key in idle:
            del _recent[key]  # buckets never outlive their window, whatever the number of clients
        window = _recent[client]
        while window and now - window[0] > _WINDOW_S:
            window.popleft()
        if len(window) >= _MESSAGES_PER_WINDOW:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many chat messages; try again in a minute")
        window.append(now)


def _resolve_context(state: AppState, body: ChatContextBody | None) -> ChatContext | None:
    """The context page must be one the reader may open: unknown and withheld paths are both 404,
    so the endpoint is no oracle for withheld pages (same rule as ``POST /profile/views``)."""
    if body is None:
        return None
    doc = service.readable_page(state.catalog(), state.store.latest_completed(), body.path)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page at '{body.path}'")
    return ChatContext(path=doc.rel_path, title=doc.title, selection=body.selection)


def _record_turn(state: AppState, user: User | None, body: ChatBody, result: ChatAnswer, duration_ms: int) -> None:
    """One telemetry line per turn (``chat/telemetry.py``): the turn's shape, never its text. The persona
    is the signed-in reader's, when there is one. A failure here is logged and never fails the request."""
    try:
        persona = state.profiles.load(user.storage_key).persona if user is not None else None
        telemetry.record(
            state.root,
            mode=body.mode,
            lang=body.lang,
            persona=persona,
            sources=[source["path"] for source in result.sources],
            refused=not result.error and not result.sources,
            cost_usd=result.cost_usd,
            duration_ms=duration_ms,
        )
    except Exception as exc:  # the type only: a filesystem error message may name the path
        log.warning("chat telemetry was not recorded (%s)", type(exc).__name__)


@router.post("/chat")
async def chat(
    body: ChatBody, request: Request, state: AppState = Depends(get_state), user: User | None = Depends(current_user)
) -> dict:
    _throttle(request.client.host if request.client else "unknown")
    ledger = ledger_for(state.root)
    # Today's total is re-read from disk (off the event loop) so every worker sees the one ceiling.
    if await run_in_threadpool(ledger.today_total) >= state.settings.chat_daily_budget_usd:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, BUDGET_SPENT)
    # The catalog stamp is a stat sweep over every page: off the event loop, like the sync page routes.
    context = await run_in_threadpool(_resolve_context, state, body.context)
    history = [ChatTurn(role=t.role, content=t.content) for t in body.history]
    started = time.monotonic()
    result = await run_chat(
        state.settings, state.root, body.message, history, lang=body.lang, mode=body.mode, context=context
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    if result.cost_usd is not None:  # a billed turn counts whether or not it produced an answer
        await run_in_threadpool(ledger.add, result.cost_usd)
    await run_in_threadpool(_record_turn, state, user, body, result, duration_ms)  # success and 502 alike
    if result.error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, result.error)
    answer = {"answer": result.answer, "sources": result.sources}
    return {**answer, "quiz": result.quiz} if result.quiz is not None else answer
