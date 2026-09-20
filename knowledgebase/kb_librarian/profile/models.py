"""The reader record: page paths, timestamps and counts, the chosen persona and the session epoch —
never page text, never free text from the reader."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

MAX_VIEWED = 500  # oldest views are dropped past this: a reading history, not an audit log
MAX_QUIZZES = 200  # likewise the oldest quiz results: the record cannot grow without bound


def now() -> datetime:
    return datetime.now(UTC)


class PageVisit(BaseModel):
    first_at: datetime = Field(default_factory=now)
    last_at: datetime = Field(default_factory=now)
    count: int = 1


class QuizResult(BaseModel):
    path: str
    at: datetime = Field(default_factory=now)
    score: int
    total: int


class Profile(BaseModel):
    sub: str
    persona: str | None = None
    viewed: dict[str, PageVisit] = Field(default_factory=dict)
    quizzes: list[QuizResult] = Field(default_factory=list)
    session_epoch: int = 0  # a session cookie is accepted only while it carries this value
    updated_at: datetime = Field(default_factory=now)
