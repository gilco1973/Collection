"""The knowledge-base contract (`kb.config.yaml`) as validated models.

Everything the librarian treats as a rule comes from this file, so the rules
are reviewable by humans and versioned with the content they govern.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class SectionConfig(BaseModel):
    id: str
    path: str
    title: str
    owner: str
    review_every_days: int = Field(gt=0)


class FrontmatterConfig(BaseModel):
    required: list[str]
    status_values: list[str]
    audience_values: list[str]


class TaxonomyConfig(BaseModel):
    tags: list[str]


class LinksConfig(BaseModel):
    trusted_hosts: list[str] = Field(default_factory=list)


class FreshnessConfig(BaseModel):
    default_days: int = Field(default=180, gt=0)
    allow_page_override: bool = True


class CatalogConfig(BaseModel):
    """A YAML catalog (videos, resources) the librarian validates and scans."""

    path: str
    required_fields: list[str]
    date_fields: list[str] = Field(default_factory=list)
    url_fields: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=list)


class StructureConfig(BaseModel):
    require_section_readme_link: bool = True


class CiConfig(BaseModel):
    blocking_severities: list[str] = Field(default_factory=lambda: ["critical", "error"])


class AtlassianConfig(BaseModel):
    confluence_space_key: str
    jira_project_key: str
    mirror_sections: list[str] = Field(default_factory=list)


class IndexConfig(BaseModel):
    owner: str
    tags: list[str] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=lambda: ["everyone"])


class I18nConfig(BaseModel):
    """Target languages for machine-translated content (`kb-librarian translate sync`)."""

    languages: list[str] = Field(default_factory=list)


class EvalThresholds(BaseModel):
    """Pass marks for ``kb-librarian eval`` (rates in [0, 1]; the cost ceiling in USD per run)."""

    citation_precision: float = Field(default=0.8, ge=0, le=1)
    citation_recall: float = Field(default=0.7, ge=0, le=1)
    refusal_correctness: float = Field(default=1.0, ge=0, le=1)
    max_cost_usd_per_run: float = Field(default=5.0, gt=0)


class KbConfig(BaseModel):
    version: int
    index: IndexConfig
    docs_root: str = "docs"
    sections: list[SectionConfig]
    frontmatter: FrontmatterConfig
    taxonomy: TaxonomyConfig
    links: LinksConfig = Field(default_factory=LinksConfig)
    freshness: FreshnessConfig = Field(default_factory=FreshnessConfig)
    catalogs: list[CatalogConfig] = Field(default_factory=list)
    structure: StructureConfig = Field(default_factory=StructureConfig)
    ci: CiConfig = Field(default_factory=CiConfig)
    atlassian: AtlassianConfig
    i18n: I18nConfig = Field(default_factory=I18nConfig)
    evals: EvalThresholds = Field(default_factory=EvalThresholds)

    @field_validator("sections")
    @classmethod
    def _unique_section_ids(cls, sections: list[SectionConfig]) -> list[SectionConfig]:
        ids = [s.id for s in sections]
        if len(ids) != len(set(ids)):
            raise ValueError("section ids must be unique")
        return sections

    def section_for(self, rel_path: str) -> SectionConfig | None:
        """Return the section whose path prefixes ``rel_path`` (docs-relative)."""
        for section in sorted(self.sections, key=lambda s: -len(s.path)):
            if rel_path == section.path or rel_path.startswith(section.path + "/"):
                return section
        return None

    def section_by_id(self, section_id: str) -> SectionConfig | None:
        return next((s for s in self.sections if s.id == section_id), None)


def load_kb_config(path: Path) -> KbConfig:
    """Load and validate ``kb.config.yaml``. Raises on any contract violation."""
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return KbConfig.model_validate(raw)


def find_kb_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) to the directory holding ``kb.config.yaml``."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "kb.config.yaml").is_file():
            return candidate
    raise FileNotFoundError("kb.config.yaml not found in this directory or any parent")
