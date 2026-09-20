"""Helpers for the evaluator tests: a golden file on the fixture KB and a prompt-routed FakeQuery."""

from pathlib import Path

import yaml

from tests.fake_query import FakeQuery, _result

GOOD_ANSWER = "Day one starts with governance. Read the onboarding page first. Then meet the owners."
REFUSAL = "That topic is not in the knowledge base."
ITEMS = [
    {
        "id": "onb-start",
        "question": "how do I get started?",
        "persona": "new-hire",
        "lang": "en",
        "expect": {"paths": ["onboarding/README.md"], "must_contain": ["governance"]},
        "tags": ["onboarding", "new-hire"],
    },
    {
        "id": "ref-cafeteria",
        "question": "¿Cuál es el menú de la cafetería?",
        "persona": "everyone",
        "lang": "es",
        "expect": {"refuse": True},
        "tags": ["refusal", "everyone"],
    },
    {
        "id": "gov-what",
        "question": "what is governance about?",
        "persona": "engineer",
        "lang": "en",
        "expect": {"paths": ["governance/README.md"], "must_contain": ["nope-not-there"]},
        "tags": ["governance", "engineer"],
    },
]


def write_golden(kb_root: Path, items: list[dict] | None = None, name: str = "golden.yaml") -> Path:
    path = kb_root / "evals" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump({"version": 1, "items": items or ITEMS}, allow_unicode=True), encoding="utf-8")
    return path


def reads(path: str, text: str, **result) -> FakeQuery:
    return FakeQuery(calls=[("get_document", {"path": path})], result=_result(result=text, **result))


def says(text: str, **result) -> FakeQuery:
    return FakeQuery(calls=[], result=_result(result=text, **result))


class Router:
    """Dispatch each chat turn to the FakeQuery whose key appears in the prompt (else ``default``)."""

    def __init__(self, routes: dict[str, FakeQuery], default: FakeQuery | None = None):
        self.routes, self.default = routes, default or says(REFUSAL)
        self.prompts: list[str] = []

    async def __call__(self, *, prompt: str, options):
        self.prompts.append(prompt)
        fake = next((f for needle, f in self.routes.items() if needle in prompt), self.default)
        async for message in fake(prompt=prompt, options=options):
            yield message


def scripted() -> Router:
    """The three ITEMS: a good cited answer, a refusal, and an answer missing its keyword."""
    return Router(
        {
            "get started": reads("onboarding/README.md", GOOD_ANSWER, total_cost_usd=0.02),
            "cafetería": says(REFUSAL, total_cost_usd=0.01),
            "governance about": reads(
                "governance/README.md", "Governance is rules. Nothing more.", total_cost_usd=0.03
            ),
        }
    )
