"""Base HTTP client for Atlassian Cloud (Confluence + Jira) with a hard write gate."""

import httpx

from kb_librarian.config import LibrarianSettings


class AtlassianNotConfigured(RuntimeError):
    """Raised when a call needs Atlassian credentials that are not present."""


class AtlassianWriteRefused(PermissionError):
    """Raised when a write is attempted without both KB_ATLASSIAN_ALLOW_WRITE and a live run."""


class AtlassianClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        allow_write: bool = False,
        dry_run: bool = True,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.allow_write = allow_write
        self.dry_run = dry_run
        self._http = httpx.Client(
            base_url=self.base_url,
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls,
        settings: LibrarianSettings,
        *,
        dry_run: bool,
        transport: httpx.BaseTransport | None = None,
    ):
        if not settings.atlassian_configured:
            raise AtlassianNotConfigured("set KB_ATLASSIAN_BASE_URL, KB_ATLASSIAN_EMAIL and KB_ATLASSIAN_API_TOKEN")
        return cls(
            settings.atlassian_base_url or "",
            settings.atlassian_email or "",
            settings.atlassian_api_token.get_secret_value() if settings.atlassian_api_token else "",
            allow_write=settings.atlassian_allow_write,
            dry_run=dry_run,
            transport=transport,
        )

    @property
    def writes_enabled(self) -> bool:
        return self.allow_write and not self.dry_run

    def ensure_write_allowed(self, what: str) -> None:
        if not self.writes_enabled:
            raise AtlassianWriteRefused(
                f"refusing to {what}: writes need KB_ATLASSIAN_ALLOW_WRITE=true and a live (non dry-run) audit"
            )

    def get(self, path: str, **params) -> dict:
        response = self._http.get(path, params=params or None)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict, what: str) -> dict:
        self.ensure_write_allowed(what)
        response = self._http.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def put(self, path: str, payload: dict, what: str) -> dict:
        self.ensure_write_allowed(what)
        response = self._http.put(path, json=payload)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._http.close()
