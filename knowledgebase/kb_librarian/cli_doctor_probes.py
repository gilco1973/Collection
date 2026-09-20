"""The ``doctor`` check record and the three probes that leave the machine (each behind its own flag).

The probes go through the project's own clients (``OidcProvider``, ``AtlassianClient``, the SDK's
``query``) with an injectable transport or query function, so tests run them against fakes.
"""

import sqlite3
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from kb_librarian.agent.options import DISALLOWED_BUILTINS
from kb_librarian.atlassian.client import AtlassianClient
from kb_librarian.auth.oidc import OidcError, OidcProvider
from kb_librarian.config import LibrarianSettings
from kb_librarian.retrieval.build import index_path
from kb_librarian.retrieval.embedder import embedder_from_settings
from kb_librarian.retrieval.index import VectorIndex

QueryFn = Callable[..., AsyncIterator[Any]]
MODEL_PROBE_BUDGET_USD = 0.05
MYSELF = "/rest/api/3/myself"


@dataclass
class Check:
    status: str  # OK | WARN | FAIL
    name: str
    detail: str

    @property
    def line(self) -> str:
        return f"{self.status} {self.name} — {self.detail}"


def ok(name: str, detail: str) -> Check:
    return Check("OK", name, detail)


def warn(name: str, detail: str) -> Check:
    return Check("WARN", name, detail)


def fail(name: str, detail: str) -> Check:
    return Check("FAIL", name, detail)


def embeddings_check(settings: LibrarianSettings, root: Path) -> Check:
    """The embedding index exists and was built by the embedder the settings configure (offline: the
    configured embedder is constructed for its model id only, never called)."""
    path = index_path(root)
    if not path.is_file():
        return warn("embeddings", "no embedding index: run kb-librarian index --embeddings")
    try:
        stats = VectorIndex(path).stats()
    except sqlite3.Error as exc:
        return fail("embeddings", f"index unreadable ({type(exc).__name__}): run kb-librarian index --embeddings")
    configured = embedder_from_settings(settings).model_id
    if stats.model_id != configured:
        detail = f"index built with model {stats.model_id!r} but the configured embedder is {configured!r}: rebuild"
        return warn("embeddings", detail)
    return ok("embeddings", f"{stats.chunks} chunks over {stats.pages} pages (model {stats.model_id})")


def idp_check(settings: LibrarianSettings, transport: httpx.BaseTransport | None = None) -> Check:
    """The discovery document is reachable, names our issuer and has https endpoints (only with SSO)."""
    if not settings.sso_configured:
        return ok("idp", "skipped: SSO not configured")
    issuer, client_id = str(settings.oidc_issuer), str(settings.oidc_client_id)
    provider = OidcProvider(issuer, client_id, str(settings.oidc_redirect_uri), transport=transport)
    try:
        provider.configuration()
    except OidcError as exc:
        return fail("idp", str(exc))
    finally:
        provider.close()
    return ok("idp", "discovery document fetched and consistent")


def atlassian_check(settings: LibrarianSettings, transport: httpx.BaseTransport | None = None) -> Check:
    """``/rest/api/3/myself`` answers with JSON for the configured credentials (only when configured)."""
    if not settings.atlassian_configured:
        return ok("atlassian-api", "skipped: Atlassian not configured")
    client = AtlassianClient.from_settings(settings, dry_run=True, transport=transport)
    try:
        client.get(MYSELF)
    except httpx.HTTPStatusError as exc:
        return fail("atlassian-api", f"returned {exc.response.status_code} for {MYSELF}")
    except httpx.HTTPError as exc:
        return fail("atlassian-api", f"unreachable ({type(exc).__name__})")
    except ValueError:
        return fail("atlassian-api", "returned a non-JSON body")
    finally:
        client.close()
    return ok("atlassian-api", f"reachable: {MYSELF} answered")


async def model_check(settings: LibrarianSettings, root: Path, query_fn: QueryFn) -> Check:
    """One capped turn with no tools at all: proves credential, model name and the SDK's CLI, nothing more."""
    options = ClaudeAgentOptions(
        system_prompt="You are a connectivity probe. Reply with the single word OK.",
        tools=[],
        allowed_tools=[],
        disallowed_tools=list(DISALLOWED_BUILTINS),
        permission_mode="default",
        max_turns=1,
        max_budget_usd=MODEL_PROBE_BUDGET_USD,
        model=settings.model,
        effort="low",
        cwd=str(root),
        setting_sources=[],
        strict_mcp_config=True,
    )
    try:
        async for message in query_fn(prompt="Reply with the single word OK.", options=options):
            if isinstance(message, ResultMessage):
                if message.is_error:
                    return fail("model", f"the turn ended in error ({message.subtype})")
                cost = message.total_cost_usd or 0.0
                return ok("model", f"one turn completed with {settings.model} (cost ${cost:.4f})")
    except Exception as exc:  # the SDK's own errors (no CLI, process failure): the type is enough
        return fail("model", f"{type(exc).__name__}: could not complete a turn")
    return fail("model", "the stream ended without a result")
