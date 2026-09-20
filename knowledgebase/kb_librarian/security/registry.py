"""The registry of reviewable modules (``security/registry.yaml``) and their content versions.

A module's *version* is a SHA-256 over (1) its registry scope (the ``paths`` list), (2) the prose of
its review sheet above the sign-off table, and (3) the sorted ``path\\0content\\0`` pairs of every
file the globs match. So it changes exactly when the reviewed code, its declared scope or what the
sheet claims about it changes — never when a sign-off row is appended. The git commit is recorded
alongside at sign time for humans; the full digest is what drift detection compares.
"""

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

REGISTRY_PATH = "security/registry.yaml"
REGISTRY_VERSION = 1
SIGNOFF_HEADING = "## Sign-off"
SHORT_CHARS = 12


class ModuleSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    kind: str = Field(pattern="^(backend|frontend|deploy|tooling)$")
    paths: list[str] = Field(min_length=1)
    tests: list[str] = Field(default_factory=list)
    sheet: str

    @field_validator("paths", "tests", "sheet")
    @classmethod
    def _inside_project(cls, value):
        for item in [value] if isinstance(value, str) else value:
            if item.startswith("/") or ".." in Path(item).parts:
                raise ValueError(f"'{item}' must be a relative path inside the project")
        return value


class Registry(BaseModel):
    version: int
    modules: list[ModuleSpec]

    def get(self, module_id: str) -> ModuleSpec:
        for module in self.modules:
            if module.id == module_id:
                return module
        raise KeyError(f"no module '{module_id}' in {REGISTRY_PATH}")


@dataclass
class ModuleVersion:
    module: ModuleSpec
    version: str  # the full digest; ``short`` is for display only
    files: list[tuple[str, str]] = field(default_factory=list)  # (relative path, per-file sha256)

    @property
    def short(self) -> str:
        return self.version[:SHORT_CHARS]


def load_registry(root: Path) -> Registry:
    with (root / REGISTRY_PATH).open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"{REGISTRY_PATH}: expected a mapping at the top level")
    registry = Registry.model_validate(raw)
    if registry.version != REGISTRY_VERSION:
        raise ValueError(f"{REGISTRY_PATH}: unsupported version {registry.version}")
    ids = [m.id for m in registry.modules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{REGISTRY_PATH}: module ids must be unique")
    return registry


def _inside(root: Path, path: Path) -> bool:
    return root.resolve() in path.resolve().parents


def module_files(root: Path, module: ModuleSpec) -> list[Path]:
    """Every regular file a module's globs match, sorted, deduplicated; symlinks (files or
    directories) and anything resolving outside the project are excluded."""
    found: set[Path] = set()
    for pattern in module.paths:
        for path in root.glob(pattern):
            if path.is_symlink() or not _inside(root, path):
                continue
            if path.is_dir():
                found.update(p for p in path.rglob("*") if p.is_file() and not p.is_symlink() and _inside(root, p))
            elif path.is_file():
                found.add(path)
    return sorted(p for p in found if "__pycache__" not in p.parts and "node_modules" not in p.parts)


def sheet_prose(root: Path, module: ModuleSpec) -> str:
    """The sheet's text above the sign-off section: what the reviewer signed against."""
    sheet = root / module.sheet
    if not sheet.is_file():
        raise ValueError(f"module '{module.id}' has no review sheet at {module.sheet}")
    lines = sheet.read_text(encoding="utf-8").split("\n")
    end = lines.index(SIGNOFF_HEADING) if SIGNOFF_HEADING in lines else len(lines)  # the exact heading line only
    return "\n".join(lines[:end])


def compute_version(root: Path, module: ModuleSpec) -> ModuleVersion:
    paths = module_files(root, module)
    if not paths:
        raise ValueError(f"module '{module.id}' matches no files: {module.paths}")
    digest = hashlib.sha256()
    digest.update(json.dumps(module.paths, sort_keys=True).encode("utf-8") + b"\0")
    digest.update(sheet_prose(root, module).encode("utf-8") + b"\0")
    files: list[tuple[str, str]] = []
    for path in paths:
        rel = path.relative_to(root).as_posix()
        content = path.read_bytes()
        files.append((rel, hashlib.sha256(content).hexdigest()))
        digest.update(rel.encode("utf-8") + b"\0" + content + b"\0")
    return ModuleVersion(module=module, version=digest.hexdigest(), files=files)


def git_commit(root: Path) -> str | None:
    """The short HEAD commit, or ``None`` outside a git checkout (never raises)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None
