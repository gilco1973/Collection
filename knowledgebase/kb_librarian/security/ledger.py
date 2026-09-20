"""Sign-off ledger: one JSON file per module under ``security/signoffs/`` plus the row in its sheet.

The ledger is the machine-readable record; the sheet's table is the human-readable copy. A sign-off
is written to both in one call — the sheet text is prepared (and can fail) *before* the ledger is
touched, so the two cannot diverge. A sign-off is bound to the module's full content version, so
``status``/``verify`` can tell a signed module from one that changed after signing.
"""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from kb_librarian.security.registry import SIGNOFF_HEADING, ModuleSpec, ModuleVersion

SIGNOFFS_DIR = "security/signoffs"
TABLE_HEADER = "| Version | Commit | Reviewer | Signature | Date | Decision | Notes |"
TABLE_RULE = "| --- | --- | --- | --- | --- | --- | --- |"
Decision = Literal["approved", "conditional", "rejected"]
Status = Literal["approved", "conditional", "rejected", "changed", "unsigned"]


class SignOff(BaseModel):
    module: str
    version: str = Field(min_length=64, max_length=64)
    commit: str | None = None
    reviewer: str = Field(min_length=1, max_length=120)
    signature: str = Field(min_length=1, max_length=4000)
    date: date
    decision: Decision
    notes: str = Field(default="", max_length=2000)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _ledger_path(root: Path, module_id: str) -> Path:
    return root / SIGNOFFS_DIR / f"{module_id}.json"


def load_signoffs(root: Path, module_id: str) -> list[SignOff]:
    path = _ledger_path(root, module_id)
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [SignOff.model_validate(item) for item in raw]


def latest_signoff(root: Path, module_id: str) -> SignOff | None:
    """The most recently recorded sign-off, by its timestamp rather than its position in the file."""
    signoffs = load_signoffs(root, module_id)
    return max(signoffs, key=lambda s: s.recorded_at) if signoffs else None


def module_status(root: Path, current: ModuleVersion) -> tuple[Status, SignOff | None]:
    """``approved``/``conditional``/``rejected`` when the last sign-off is for the current version,
    ``changed`` when the code moved on since it, ``unsigned`` when there is none."""
    last = latest_signoff(root, current.module.id)
    if last is None:
        return "unsigned", None
    if last.version != current.version:
        return "changed", last
    return last.decision, last


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def signoff_row(signoff: SignOff) -> str:
    cells = [
        signoff.version[:12],
        signoff.commit or "-",
        signoff.reviewer,
        signoff.signature,
        signoff.date.isoformat(),
        signoff.decision,
        signoff.notes or "-",
    ]
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def sheet_with_row(text: str, signoff: SignOff) -> str:
    """The sheet text with the sign-off row appended to the table of its ``## Sign-off`` section
    (created when missing). Any other table in the sheet is left alone. Raises without the section."""
    lines = text.rstrip("\n").split("\n")
    try:
        start = lines.index(SIGNOFF_HEADING)
    except ValueError:
        raise ValueError(f"sheet has no '{SIGNOFF_HEADING}' section") from None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = lines[start:end]
    if TABLE_HEADER not in section:
        section = [*section, "", TABLE_HEADER, TABLE_RULE]
    last_row = max(i for i, line in enumerate(section) if line.startswith("|"))
    section.insert(last_row + 1, signoff_row(signoff))
    return "\n".join([*lines[:start], *section, *lines[end:]]) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def record_signoff(root: Path, current: ModuleVersion, signoff: SignOff) -> Path:
    """Persist a sign-off for the module's *current* version. The sheet text is prepared first (the
    only step that can fail on content), then the sheet and the ledger are each written atomically,
    sheet first — a crash between the two leaves a sheet row without its ledger entry, which
    ``status`` reports as ``unsigned`` (never the reverse: a ledger entry nobody can see)."""
    if signoff.version != current.version:
        raise ValueError(f"sign-off version {signoff.version[:12]} is not the current version {current.short}")
    module: ModuleSpec = current.module
    sheet = root / module.sheet
    new_sheet = sheet_with_row(sheet.read_text(encoding="utf-8"), signoff)
    path = _ledger_path(root, module.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [*load_signoffs(root, module.id), signoff]
    _write_atomic(sheet, new_sheet)
    _write_atomic(path, json.dumps([e.model_dump(mode="json") for e in entries], indent=1) + "\n")
    return path
