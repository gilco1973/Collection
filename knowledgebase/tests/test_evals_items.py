"""kb_librarian/evals/items: the golden set's shape and its validation against the real catalog."""

from pathlib import Path

import pytest
import yaml

from kb_librarian.evals.items import EvalItem, GoldenError, load_golden

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _item(**overrides) -> dict:
    base = {
        "id": "onb-1",
        "question": "How do I get started?",
        "persona": "new-hire",
        "lang": "en",
        "expect": {"paths": ["onboarding/README.md"], "must_contain": ["governance"]},
        "tags": ["onboarding", "new-hire"],
    }
    base.update(overrides)
    return base


def _write(kb_root: Path, items: list[dict], version: int = 1) -> Path:
    path = kb_root / "evals" / "golden.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump({"version": version, "items": items}, allow_unicode=True), encoding="utf-8")
    return path


def test_load_golden_returns_validated_items(kb_root: Path):
    path = _write(kb_root, [_item(), _item(id="ref-1", expect={"refuse": True}, lang="es")])
    items = load_golden(path, kb_root)
    assert [i.id for i in items] == ["onb-1", "ref-1"]
    assert isinstance(items[0], EvalItem) and items[0].expect.paths == ["onboarding/README.md"]
    assert items[1].expect.refuse and items[1].expect.paths == [] and items[1].expect.must_not_contain == []


@pytest.mark.parametrize(
    ("items", "needle"),
    [
        ([_item(), _item()], "duplicate id"),
        ([_item(expect={"paths": ["onboarding/nope.md"]})], "unknown path"),
        ([_item(expect={"paths": ["onboarding/stale.md"]})], "withheld"),
        ([_item(lang="fr")], "lang"),
        ([_item(persona="wizard")], "persona"),
        ([_item(expect={"refuse": True, "paths": ["onboarding/README.md"]})], "refuse"),
    ],
)
def test_load_golden_rejects_bad_items(kb_root: Path, items: list[dict], needle: str):
    path = _write(kb_root, items)
    with pytest.raises(GoldenError) as info:
        load_golden(path, kb_root)
    assert needle in str(info.value)


def test_load_golden_rejects_a_bad_file(kb_root: Path):
    with pytest.raises(GoldenError, match="version"):
        load_golden(_write(kb_root, [_item()], version=2), kb_root)
    empty = kb_root / "evals" / "empty.yaml"
    empty.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(GoldenError, match="mapping"):
        load_golden(empty, kb_root)
    with pytest.raises(GoldenError, match="not found"):
        load_golden(kb_root / "evals" / "missing.yaml", kb_root)
    with pytest.raises(GoldenError, match="no items"):
        load_golden(_write(kb_root, []), kb_root)


def test_the_project_golden_set_validates_against_the_real_docs_tree():
    items = load_golden(PROJECT_ROOT / "evals" / "golden.yaml", PROJECT_ROOT)
    assert len(items) >= 50
    langs = {lang: sum(1 for i in items if i.lang == lang) for lang in ("en", "es", "he")}
    assert langs["es"] >= 10 and langs["he"] >= 5
    assert sum(1 for i in items if i.expect.refuse) >= 6
    for item in items:
        assert item.tags, item.id
        if not item.expect.refuse:
            assert item.expect.paths and item.expect.must_contain, item.id


def test_the_contract_carries_the_eval_thresholds(kb_config):
    from kb_librarian.kbconfig import EvalThresholds, load_kb_config

    assert kb_config.evals == EvalThresholds()  # the fixture has no block: defaults apply
    real = load_kb_config(PROJECT_ROOT / "kb.config.yaml").evals
    assert (real.citation_precision, real.citation_recall, real.refusal_correctness) == (0.8, 0.7, 1.0)
    assert real.max_cost_usd_per_run == 5.0 and "max_cost_usd_per_run" in real.model_dump()
    with pytest.raises(ValueError):
        EvalThresholds(citation_precision=1.5)
