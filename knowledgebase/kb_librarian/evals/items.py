"""The golden set (``evals/golden.yaml``): item shape and validation against the catalog.

Every expected path must be a page in the catalog that readers may open. A withheld page (a
sensitive hit in its text) can only be the *subject* of a ``refuse: true`` item, and such an
item lists no paths: the chat cannot read the page, so the right answer is a refusal.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.kbconfig import load_kb_config

GOLDEN_VERSION = 1
DEFAULT_GOLDEN = Path("evals") / "golden.yaml"


class GoldenError(ValueError):
    """The golden file is malformed or names something the knowledge base does not have."""


class Expectation(BaseModel):
    paths: list[str] = Field(default_factory=list)
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    refuse: bool = False

    @model_validator(mode="after")
    def _refusals_cite_nothing(self) -> "Expectation":
        if self.refuse and self.paths:
            raise ValueError("a refuse item lists no paths (a refusal cites nothing)")
        return self


class EvalItem(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    persona: str = Field(min_length=1)
    lang: str = "en"
    expect: Expectation = Field(default_factory=Expectation)
    tags: list[str] = Field(default_factory=list)


class GoldenSet(BaseModel):
    version: int
    items: list[EvalItem]


def _parse(path: Path) -> GoldenSet:
    if not path.is_file():
        raise GoldenError(f"golden file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise GoldenError(f"{path}: expected a mapping at the top level")
    try:
        golden = GoldenSet.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise GoldenError(f"{path}: {problems}") from None
    if golden.version != GOLDEN_VERSION:
        raise GoldenError(f"{path}: unsupported version {golden.version} (expected {GOLDEN_VERSION})")
    if not golden.items:
        raise GoldenError(f"{path}: no items")
    return golden


def load_golden(path: Path, root: Path) -> list[EvalItem]:
    """Load ``path`` and check every item against the knowledge base at ``root``: unique ids, expected
    paths that exist and are not withheld, a configured language (or ``en``), a known persona."""
    golden = _parse(path)
    config = load_kb_config(root / "kb.config.yaml")
    catalog = load_catalog(root, config)
    languages = {"en", *config.i18n.languages}
    personas = set(config.frontmatter.audience_values)
    problems: list[str] = []
    seen: set[str] = set()
    for item in golden.items:
        if item.id in seen:
            problems.append(f"{item.id}: duplicate id")
        seen.add(item.id)
        if item.lang not in languages:
            problems.append(f"{item.id}: lang '{item.lang}' is not configured (choose from {sorted(languages)})")
        if item.persona not in personas:
            problems.append(f"{item.id}: persona '{item.persona}' is not an audience value")
        for rel in item.expect.paths:
            doc = catalog.get(rel)
            if doc is None:
                problems.append(f"{item.id}: unknown path '{rel}'")
            elif doc.sensitive:
                problems.append(f"{item.id}: '{rel}' is withheld; it may only be the subject of a refuse item")
    if problems:
        raise GoldenError(f"{path}: " + "; ".join(problems))
    return golden.items
