"""Shared scaffolding for the ``kb-librarian doctor`` tests."""

import argparse
import io
from pathlib import Path

from kb_librarian.cli_doctor import cmd_doctor
from kb_librarian.config import LibrarianSettings
from kb_librarian.kbconfig import load_kb_config
from kb_librarian.retrieval.build import build_index, index_path
from kb_librarian.retrieval.embedder import HashEmbedder

# Everything the doctor reads from the environment besides the model credential.
ENV_KEYS = (
    "KB_ALLOW_LIVE",
    "KB_API_KEY",
    "KB_SESSION_SECRET",
    "KB_OIDC_ISSUER",
    "KB_OIDC_CLIENT_ID",
    "KB_OIDC_CLIENT_SECRET",
    "KB_OIDC_REDIRECT_URI",
    "KB_ATLASSIAN_BASE_URL",
    "KB_ATLASSIAN_EMAIL",
    "KB_ATLASSIAN_API_TOKEN",
    "KB_ATLASSIAN_ALLOW_WRITE",
    "KB_PROFILE_RETENTION_DAYS",
    "KB_EMBED_URL",
    "KB_EMBED_MODEL",
    "KB_EMBED_API_KEY",
    "KB_EMBED_DIM",
    "CLAUDE_CODE_OAUTH_TOKEN",
)
FAKE_CREDENTIAL = "sk-test-" + "x" * 32  # 40 characters: the "medium" length class


class WithRetention(LibrarianSettings):
    """Carries the retention setting the doctor reports on (a lifecycle field) so a clean host exits 0."""

    profile_retention_days: int | None = 30


def with_index(root: Path) -> None:
    """A ready host has an embedding index (hash embedder: offline); the doctor warns without one."""
    build_index(root, load_kb_config(root / "kb.config.yaml"), HashEmbedder())


def run_doctor(
    settings, root: Path, *, network: bool = False, model: bool = False, index: bool = True, **inject
) -> tuple[int, list[str]]:
    if index and not index_path(root).is_file():
        with_index(root)
    out = io.StringIO()
    args = argparse.Namespace(command="doctor", network=network, model=model)
    code = cmd_doctor(settings, root, args, out, **inject)
    return code, out.getvalue().splitlines()
