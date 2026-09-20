"""Per-reader endpoints: profile with reading progress, persona, page views, quiz results, forget-me.

Every route needs a signed-in reader (``require_user``); a reader only ever reaches their own
record because the subject comes from the session cookie, never from the request body.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator

from kb_librarian.api import service
from kb_librarian.api.deps import AppState, get_state, require_user
from kb_librarian.auth.session import User
from kb_librarian.catalog.catalog import Document
from kb_librarian.profile.store import Profile, QuizResult

router = APIRouter()
GENERIC_AUDIENCE = "everyone"  # not a persona: the value pages use to mean "for all readers"
MAX_QUIZ_TOTAL = 10


class PersonaBody(BaseModel):
    persona: str | None = Field(default=None, max_length=40)


class ViewBody(BaseModel):
    path: str = Field(min_length=1, max_length=400)


class QuizBody(BaseModel):
    """A quiz the reader graded in the console: only the page and the tally are stored."""

    path: str = Field(min_length=1, max_length=400)
    score: int = Field(ge=0, le=MAX_QUIZ_TOTAL)
    total: int = Field(ge=1, le=MAX_QUIZ_TOTAL)

    @model_validator(mode="after")
    def _score_within_total(self) -> "QuizBody":
        if self.score > self.total:
            raise ValueError("score cannot exceed total")
        return self


def _readable_page(state: AppState, path: str) -> Document:
    """A page that exists and is not withheld; anything else is 404 (a withheld page is never 'read')."""
    doc = service.readable_page(state.catalog(), state.store.latest_completed(), path)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page at '{path}'")
    return doc


def personas(state: AppState) -> list[str]:
    """The personas a reader may choose: the contract's audience values minus the generic one."""
    return [a for a in state.config.frontmatter.audience_values if a != GENERIC_AUDIENCE]


def _progress(state: AppState, profile: Profile) -> list[dict]:
    catalog = state.catalog()
    out = []
    for section in state.config.sections:
        paths = [d.rel_path for d in catalog.in_section(section.id)]
        viewed = [p for p in paths if p in profile.viewed]
        out.append({"section": section.id, "title": section.title, "viewed": len(viewed), "total": len(paths)})
    return out


def _view(state: AppState, profile: Profile) -> dict:
    catalog = state.catalog()
    docs = {d.rel_path: d for d in catalog.documents}
    # A page withheld *since* it was read must not come back with its title (or confirm its path): same
    # rule as /api/pages — the history is served through the withholding filter, never around it.
    hidden = service.withheld_paths(catalog, state.store.latest_completed())
    return {
        "persona": profile.persona,
        "personas": personas(state),
        "viewed": {
            p: {**v.model_dump(mode="json"), "title": docs[p].title}
            for p, v in profile.viewed.items()
            if p in docs and p not in hidden
        },
        "quizzes": [q.model_dump(mode="json") for q in profile.quizzes],
        "progress": _progress(state, profile),
        "updated_at": profile.updated_at.isoformat(),
    }


@router.get("/profile")
def get_profile(user: User = Depends(require_user), state: AppState = Depends(get_state)) -> dict:
    return _view(state, state.profiles.load(user.storage_key))


@router.put("/profile/persona")
def set_persona(body: PersonaBody, user: User = Depends(require_user), state: AppState = Depends(get_state)) -> dict:
    if body.persona is not None and body.persona not in personas(state):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"persona must be one of {personas(state)}")
    return _view(state, state.profiles.set_persona(user.storage_key, body.persona))


@router.post("/profile/views", status_code=status.HTTP_201_CREATED)
def record_view(body: ViewBody, user: User = Depends(require_user), state: AppState = Depends(get_state)) -> dict:
    doc = _readable_page(state, body.path)
    profile = state.profiles.record_view(user.storage_key, doc.rel_path)
    return {"path": doc.rel_path, "count": profile.viewed[doc.rel_path].count}


@router.post("/profile/quizzes", status_code=status.HTTP_201_CREATED)
def record_quiz(body: QuizBody, user: User = Depends(require_user), state: AppState = Depends(get_state)) -> dict:
    doc = _readable_page(state, body.path)
    profile = state.profiles.record_quiz(
        user.storage_key, QuizResult(path=doc.rel_path, score=body.score, total=body.total)
    )
    return profile.quizzes[-1].model_dump(mode="json")


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
def forget_me(user: User = Depends(require_user), state: AppState = Depends(get_state)) -> Response:
    state.profiles.delete(user.storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
