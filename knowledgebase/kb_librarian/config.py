"""Runtime settings for the librarian, read from the environment (prefix ``KB_``).

Credentials for Claude itself (``ANTHROPIC_API_KEY`` / ``CLAUDE_CODE_OAUTH_TOKEN``)
are read by the Agent SDK directly and are never stored here.
"""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
MIN_SESSION_SECRET_CHARS = 32
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_secure_url(url: str) -> bool:
    """https, or plain http only to the local machine (a developer's IdP or console)."""
    parts = urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http" and (parts.hostname or "") in _LOCAL_HOSTS)


def settings_errors(exc: ValidationError) -> list[str]:
    """One ``KB_<VARIABLE>: <reason>`` line per rejected setting — the reason only, never the value."""
    return sorted(f"KB_{'.'.join(str(part) for part in err['loc']).upper()}: {err['msg']}" for err in exc.errors())


class LibrarianSettings(BaseSettings):
    """Read from the process environment only: no ``.env`` file is ever consulted, so a
    stray file in the working directory cannot flip the live or write gates."""

    # env_ignore_empty: a variable rendered empty by a ConfigMap, a secret template or `.env.example`
    # reads as unset (the type's default), never as an empty string a validator would reject.
    model_config = SettingsConfigDict(env_prefix="KB_", env_file=None, extra="ignore", env_ignore_empty=True)

    model: str = "claude-opus-5"
    effort: EffortLevel = "high"
    api_key: SecretStr | None = None
    max_turns: int = Field(default=40, gt=0)
    max_budget_usd: float = Field(default=2.0, gt=0)
    # Chat is a single Q&A turn, not a full audit: its own, much smaller ceiling.
    chat_max_turns: int = Field(default=6, gt=0)
    chat_max_budget_usd: float = Field(default=0.5, gt=0)
    # Server-side gate: unless true, every audit is forced to dry-run, whatever
    # the caller asked for. Mirrors the "a leaked key can never mutate" rule.
    allow_live: bool = False
    reports_dir: str = ".librarian/reports"
    # API limits: stored reader problem reports (count) and the daily spend ceiling summed from reports.
    max_problem_reports: int = Field(default=500, gt=0)
    daily_budget_usd: float = Field(default=20.0, gt=0)
    # Operational readiness: the root logger's level and format (structured JSON by default), and the
    # chat's own daily ceiling, summed over every client from the ledger at .librarian/chat-spend.json.
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    chat_daily_budget_usd: float = Field(default=25.0, gt=0)
    # Retrieval: the embedding endpoint behind `kb-librarian index --embeddings` and semantic search
    # (OpenAI-compatible or Voyage-style, https only). Unset = the offline hash embedder of KB_EMBED_DIM
    # buckets (token overlap, no synonyms), so nothing leaves the host.
    embed_url: str | None = None
    embed_model: str = ""
    embed_api_key: SecretStr | None = None
    embed_dim: int = Field(default=256, gt=0)

    atlassian_base_url: str | None = None
    atlassian_email: str | None = None
    atlassian_api_token: SecretStr | None = None
    atlassian_allow_write: bool = False

    # Enterprise identity: OpenID Connect (authorization code + PKCE) against the organisation's IdP.
    # Sessions are an HMAC-signed cookie; without every one of these the console has no sign-in.
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None  # optional: a public client relies on PKCE alone
    oidc_redirect_uri: str | None = None
    oidc_scopes: str = "openid profile email"
    session_secret: SecretStr | None = None
    session_ttl_hours: int = Field(default=12, gt=0, le=24 * 30)
    # Operator role from identity: the ID-token claim that lists the person's groups, and the groups
    # (comma-separated) that grant the role. Empty = a sign-in never grants it (KB_API_KEY alone does).
    oidc_groups_claim: str = "groups"
    oidc_operator_groups: str = ""

    @field_validator("oidc_issuer", "oidc_redirect_uri", "embed_url")
    @classmethod
    def _https_only(cls, value: str | None, info) -> str | None:
        if value is not None and not is_secure_url(value):
            raise ValueError(f"{info.field_name} must be an https URL (http is allowed only for localhost)")
        return value

    @field_validator("embed_model")
    @classmethod
    def _model_with_endpoint(cls, value: str, info) -> str:
        if info.data.get("embed_url") and not value.strip():
            raise ValueError("KB_EMBED_MODEL is required when KB_EMBED_URL is set")
        return value.strip()

    @field_validator("session_secret")
    @classmethod
    def _strong_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < MIN_SESSION_SECRET_CHARS:
            raise ValueError(f"KB_SESSION_SECRET must be at least {MIN_SESSION_SECRET_CHARS} characters")
        return value

    @field_validator("log_level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in LOG_LEVELS:
            raise ValueError(f"KB_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
        return level

    @property
    def sso_configured(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_redirect_uri and self.session_secret)

    @property
    def cookies_secure(self) -> bool:
        """Session cookies carry ``Secure`` whenever the console is served over https — decided from the
        configured redirect URI, not from what a proxy forwards, so a missing X-Forwarded-Proto fails safe."""
        return bool(self.oidc_redirect_uri and self.oidc_redirect_uri.startswith("https://"))

    @property
    def operator_groups(self) -> frozenset[str]:
        """Group names that grant the operator role at sign-in (split on commas, stripped, empty dropped)."""
        return frozenset(name.strip() for name in self.oidc_operator_groups.split(",") if name.strip())

    def resolve_dry_run(self, requested_dry_run: bool) -> bool:
        """Force dry-run unless live runs are explicitly enabled server-side."""
        if self.allow_live:
            return requested_dry_run
        return True

    @property
    def atlassian_configured(self) -> bool:
        return bool(self.atlassian_base_url and self.atlassian_email and self.atlassian_api_token)

    # Data lifecycle: reader records untouched for this many days are removed by the deployment's
    # scheduled `kb-librarian profiles purge --live`. None = no automatic purge; the CLI then needs an
    # explicit --older-than-days.
    profile_retention_days: int | None = Field(default=None, gt=0)
    # Insights: chat telemetry lines (.librarian/chat-log.jsonl) older than this are dropped by
    # `kb-librarian insights prune`; a page needs at least this many distinct readers before any
    # reader-derived count of it is reported (k-anonymity in the collector).
    chat_log_days: int = Field(default=90, gt=0)
    insights_k: int = Field(default=5, gt=0)
