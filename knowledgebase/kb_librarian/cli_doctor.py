"""``kb-librarian doctor``: readiness checks an operator runs on a host before (and after) deploying.

One line per check — ``OK|WARN|FAIL name — detail`` — and exit 0 when every check is OK, 1 when
something warrants attention, 2 when anything failed. Secrets are reported by presence and length
class only; no value ever reaches the output. Only ``--network`` and ``--model`` leave the machine
(``cli_doctor_probes.py``).
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
from claude_agent_sdk import query as sdk_query

from kb_librarian.api.observability import probe_writable
from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.cli_commands import EXIT_FAILED, EXIT_FINDINGS, EXIT_OK
from kb_librarian.cli_doctor_probes import (
    MODEL_PROBE_BUDGET_USD,
    Check,
    QueryFn,
    atlassian_check,
    embeddings_check,
    fail,
    idp_check,
    model_check,
    ok,
    warn,
)
from kb_librarian.config import MIN_SESSION_SECRET_CHARS, LibrarianSettings
from kb_librarian.kbconfig import load_kb_config

MIN_API_KEY_CHARS = 16
CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
SSO_VARS = {
    "KB_OIDC_ISSUER": "oidc_issuer",
    "KB_OIDC_CLIENT_ID": "oidc_client_id",
    "KB_OIDC_REDIRECT_URI": "oidc_redirect_uri",
    "KB_SESSION_SECRET": "session_secret",
}
ATLASSIAN_VARS = {
    "KB_ATLASSIAN_BASE_URL": "atlassian_base_url",
    "KB_ATLASSIAN_EMAIL": "atlassian_email",
    "KB_ATLASSIAN_API_TOKEN": "atlassian_api_token",
}
CLI_CREDENTIAL_STORE = Path("~/.claude/.credentials.json")  # the Agent SDK's bundled CLI keeps its own sign-in here
NO_CREDENTIAL = (
    "neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN is set and the bundled CLI holds no credential store:"
    " a proxy may still supply one — doctor --model is the authoritative probe"
)
NO_RETENTION = "KB_PROFILE_RETENTION_DAYS not set: reader profiles are never purged automatically"


def length_class(value: str) -> str:
    """The size band of a secret — the only thing ever said about its value."""
    return "short" if len(value) < 16 else "medium" if len(value) < 48 else "long"


def _value(settings: LibrarianSettings, field: str) -> str | None:
    """A setting's string value, unwrapping ``SecretStr``; ``None`` when unset or empty."""
    value = getattr(settings, field, None)
    if value is not None and hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return value or None


def _all_or_none(settings: LibrarianSettings, name: str, variables: dict[str, str]) -> Check:
    missing = [var for var, field in variables.items() if not _value(settings, field)]
    if not missing:
        return ok(name, "configured")
    if len(missing) == len(variables):
        return ok(name, "not configured")
    return fail(name, "partially configured: missing " + ", ".join(missing))


def _secret_length(settings: LibrarianSettings, name: str, field: str, var: str, minimum: int) -> Check:
    value = _value(settings, field)
    if value is None:
        return ok(name, f"{var} not set" + (" (no break-glass operator key)" if field == "api_key" else ""))
    if len(value) < minimum:
        return fail(name, f"{var} is shorter than {minimum} characters")
    return ok(name, f"{var} set ({length_class(value)})")


def _python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if tuple(sys.version_info[:2]) == (3, 11):
        return ok("python", version)
    return fail("python", f"{version}; 3.11 is required")


def _project(root: Path) -> list[Check]:
    try:
        config = load_kb_config(root / "kb.config.yaml")
    except Exception as exc:  # the type is enough: the message may name paths
        return [
            fail("kb-config", f"does not load ({type(exc).__name__})"),
            fail("catalog", "skipped: kb.config.yaml did not load"),
        ]
    try:
        count = len(load_catalog(root, config).documents)
    except Exception as exc:
        return [ok("kb-config", "loads"), fail("catalog", f"does not load ({type(exc).__name__})")]
    return [ok("kb-config", "loads"), ok("catalog", f"{count} pages")]


def _state_dir(root: Path) -> Check:
    if probe_writable(root / ".librarian"):
        return ok("state-dir", ".librarian/ is writable")
    return fail("state-dir", ".librarian/ is not writable")


def _credentials() -> Check:
    present = [var for var in CREDENTIAL_VARS if os.environ.get(var)]
    if present:
        return ok("credentials", ", ".join(f"{var} set ({length_class(os.environ[var])})" for var in present))
    if CLI_CREDENTIAL_STORE.expanduser().is_file():
        return ok("credentials", "no credential variable, but the bundled CLI holds its own credential store")
    return warn("credentials", NO_CREDENTIAL)


def _live_gate(settings: LibrarianSettings) -> Check:
    if settings.allow_live:
        return warn("live-gate", "KB_ALLOW_LIVE=true: live audits may change pages")
    return ok("live-gate", "KB_ALLOW_LIVE off: every audit is forced to dry-run")


def _write_gate(settings: LibrarianSettings) -> Check:
    if not settings.atlassian_allow_write:
        return ok("atlassian-write-gate", "KB_ATLASSIAN_ALLOW_WRITE off")
    if not settings.atlassian_configured:
        return warn("atlassian-write-gate", "KB_ATLASSIAN_ALLOW_WRITE=true but Atlassian is not configured")
    return warn("atlassian-write-gate", "KB_ATLASSIAN_ALLOW_WRITE=true: live runs may write to Confluence and Jira")


def _retention(settings: LibrarianSettings) -> Check:
    days = getattr(settings, "profile_retention_days", None)  # the lifecycle setting; None = no automatic purge
    if days is None:
        return warn("retention", NO_RETENTION)
    return ok("retention", f"reader profiles inactive for {days} days are purged")


def offline_checks(settings: LibrarianSettings, root: Path) -> list[Check]:
    return [
        _python(),
        *_project(root),
        _state_dir(root),
        _credentials(),
        _secret_length(settings, "api-key", "api_key", "KB_API_KEY", MIN_API_KEY_CHARS),
        _all_or_none(settings, "sso", SSO_VARS),
        _secret_length(settings, "session-secret", "session_secret", "KB_SESSION_SECRET", MIN_SESSION_SECRET_CHARS),
        _live_gate(settings),
        _all_or_none(settings, "atlassian", ATLASSIAN_VARS),
        _write_gate(settings),
        _retention(settings),
        embeddings_check(settings, root),
    ]


def add_doctor_parser(sub) -> None:
    doctor = sub.add_parser(
        "doctor", help="readiness checks (runtime, project, state dir, credentials, gates); exit 0/1/2"
    )
    doctor.add_argument(
        "--network", action="store_true", help="also reach the identity provider and Atlassian, when configured"
    )
    doctor.add_argument(
        "--model",
        action="store_true",
        help=f"also run one minimal model turn (max_turns=1, at most ${MODEL_PROBE_BUDGET_USD})",
    )


def cmd_doctor(
    settings: LibrarianSettings,
    root: Path,
    args,
    out,
    *,
    query_fn: QueryFn | None = None,
    oidc_transport: httpx.BaseTransport | None = None,
    atlassian_transport: httpx.BaseTransport | None = None,
) -> int:
    checks = offline_checks(settings, root)
    if args.network:
        checks += [idp_check(settings, oidc_transport), atlassian_check(settings, atlassian_transport)]
    if args.model:
        checks.append(asyncio.run(model_check(settings, root, query_fn or sdk_query)))
    for check in checks:
        print(check.line, file=out)
    statuses = {check.status for check in checks}
    if "FAIL" in statuses:
        return EXIT_FAILED
    return EXIT_FINDINGS if "WARN" in statuses else EXIT_OK
