"""The insights file: per-page aggregates and the unanswered-question counts. Paths, counts and rates only."""

from datetime import datetime

from pydantic import BaseModel, Field


class PageInsight(BaseModel):
    """One readable page. The reader-derived numbers (``views``, ``readers``, ``quiz_attempts``,
    ``quiz_fail_rate``) are ``None`` when fewer than ``k`` distinct readers opened the page in the
    window; problem counts and chat citations are not derived from reader records and always show."""

    views: int | None = None
    readers: int | None = None
    problems: dict[str, int] = Field(default_factory=dict)
    quiz_attempts: int | None = None
    quiz_fail_rate: float | None = None
    chat_citations: int = 0


class Insights(BaseModel):
    generated_at: datetime
    k: int
    window_days: int
    pages: dict[str, PageInsight] = Field(default_factory=dict)
    unanswered: dict[str, dict[str, int]] = Field(default_factory=lambda: {"mode": {}, "lang": {}})
    suppressed: int = 0  # pages whose reader-derived numbers were withheld for being below k
