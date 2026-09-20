"""Application state and authorisation for the API."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from kb_librarian.agent.task_manager import AuditTaskManager
from kb_librarian.auth.oidc import OidcProvider
from kb_librarian.auth.principal import Principal, principal_for
from kb_librarian.auth.session import SESSION_COOKIE, User, user_from_session
from kb_librarian.catalog.catalog import Catalog, load_catalog
from kb_librarian.config import LibrarianSettings
from kb_librarian.i18n.localize import localize
from kb_librarian.kbconfig import KbConfig, load_kb_config
from kb_librarian.profile.store import ProfileStore
from kb_librarian.reports import ReportStore
from kb_librarian.retrieval.state import Retriever, RetrieverCache

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AppState:
    root: Path
    settings: LibrarianSettings
    config: KbConfig
    store: ReportStore
    manager: AuditTaskManager
    profiles: ProfileStore
    tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=lambda: defaultdict(asyncio.Lock))
    admission: asyncio.Lock = field(default_factory=asyncio.Lock)  # held from validation to registration
    reserved_budgets: dict[str, float] = field(default_factory=dict)  # budget of every audit still running
    _catalog: Catalog | None = None
    _catalog_stamp: tuple[int, int, int] | None = None
    oidc_transport: httpx.BaseTransport | None = None  # tests inject a fake identity provider here
    _oidc: OidcProvider | None = None
    _retrievers: RetrieverCache = field(default_factory=RetrieverCache)

    def oidc(self) -> OidcProvider | None:
        """The relying party, built on first use; ``None`` when SSO is not configured (no sign-in)."""
        if not self.settings.sso_configured:
            return None
        if self._oidc is None:
            s = self.settings
            self._oidc = OidcProvider(
                str(s.oidc_issuer),
                str(s.oidc_client_id),
                str(s.oidc_redirect_uri),
                client_secret=s.oidc_client_secret.get_secret_value() if s.oidc_client_secret else None,
                scopes=s.oidc_scopes,
                transport=self.oidc_transport,
            )
        return self._oidc

    def retriever(self) -> Retriever | None:
        """Semantic search over ``.librarian/index/embeddings.sqlite``: ``None`` without an index file,
        built on first use and replaced when the file changes (the nightly ``index --embeddings``)."""
        return self._retrievers.get(self.root, self.settings)

    @property
    def session_secret(self) -> str:
        if self.settings.session_secret is None:
            raise RuntimeError("KB_SESSION_SECRET is not set")
        return self.settings.session_secret.get_secret_value()

    def catalog(self) -> Catalog:
        """The docs catalog, reloaded only when a page's mtime or the page count changes."""
        docs_root = self.root / self.config.docs_root
        files = [p for p in docs_root.rglob("*.md") if p.is_file()]
        stats = [p.stat() for p in files]
        # Sums, not a max: an edit changes the stamp even when another file carries a future mtime.
        stamp = (len(files), sum(s.st_mtime_ns for s in stats), sum(s.st_size for s in stats))
        if self._catalog is None or stamp != self._catalog_stamp:
            self._catalog = load_catalog(self.root, self.config)
            self._catalog_stamp = stamp
        return self._catalog

    def catalog_for(self, lang: str | None) -> tuple[Catalog, set[str]]:
        """The catalog a request should read: localized to ``lang`` when it names a configured
        language, English otherwise. The whitelist check lives here — nowhere else reads ``lang``
        off a request before it has passed this, so a caller can never walk out of ``docs/i18n/``."""
        base = self.catalog()
        if lang and lang in self.config.i18n.languages:
            return localize(base, self.root / self.config.docs_root, lang)
        return base, set()

    @property
    def operator_key(self) -> str | None:
        return self.settings.api_key.get_secret_value() if self.settings.api_key else None

    def lock_for(self, audit_id: str) -> asyncio.Lock:
        return self.locks[audit_id]


def reconcile_orphans(store: ReportStore, manager: AuditTaskManager) -> list[str]:
    """Mark reports left ``in_progress`` by a dead process as failed (nothing can finish them)."""
    orphaned: list[str] = []
    for entry in store.entries():
        if entry.status == "in_progress" and entry.audit_id not in manager.running():
            report = store.load(entry.audit_id)
            report.finish("failed", error="orphaned: the process running this audit is gone")
            store.save(report)
            manager.unregister(entry.audit_id)
            orphaned.append(entry.audit_id)
    return orphaned


def build_state(root: Path, settings: LibrarianSettings | None = None) -> AppState:
    settings = settings or LibrarianSettings()
    manager = AuditTaskManager()
    manager.configure(root)
    store = ReportStore(root / settings.reports_dir)
    reconcile_orphans(store, manager)
    return AppState(
        root=root,
        settings=settings,
        config=load_kb_config(root / "kb.config.yaml"),
        store=store,
        manager=manager,
        profiles=ProfileStore(root),
    )


def get_state(request: Request) -> AppState:
    return request.app.state.kb


def _principal(state: AppState, credentials: HTTPAuthorizationCredentials | None, user: User | None) -> Principal:
    key = state.session_secret.encode("utf-8") if state.settings.session_secret else None
    return principal_for(state.operator_key, credentials.credentials if credentials else None, user, key)


def role_for(state: AppState, credentials: HTTPAuthorizationCredentials | None, user: User | None) -> str:
    """``operator`` when the bearer token matches ``KB_API_KEY`` or the session says so; otherwise ``viewer``."""
    return _principal(state, credentials, user).role


def current_user(request: Request, state: AppState = Depends(get_state)) -> User | None:
    """The signed-in person, from the session cookie; ``None`` when anonymous, SSO is off, or the cookie
    predates the reader's current session epoch ("sign out everywhere")."""
    if not state.settings.sso_configured:
        return None
    user = user_from_session(request.cookies.get(SESSION_COOKIE), state.session_secret)
    if user is None or user.epoch != state.profiles.session_epoch(user.storage_key):
        return None
    return user


def current_principal(
    state: AppState = Depends(get_state),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    user: User | None = Depends(current_user),
) -> Principal:
    return _principal(state, credentials, user)


def current_role(principal: Principal = Depends(current_principal)) -> str:
    return principal.role


def same_origin(request: Request) -> None:
    """Refuse a cookie-authenticated request that a foreign site initiated (CSRF).

    ``Sec-Fetch-Site`` is the browser's own verdict; when absent (older clients, non-browsers) the
    ``Origin`` host must match ours. A request with neither header is a same-origin or non-browser
    call and passes — a cross-site browser request always carries at least one of them.
    """
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cross-site request refused")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cross-site request refused")


def require_user(user: User | None = Depends(current_user), _: None = Depends(same_origin)) -> User:
    """A signed-in reader on a same-origin request: what every per-user route depends on."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in to use this")
    return user


def require_operator(request: Request, principal: Principal = Depends(current_principal)) -> Principal:
    """An operator by key or by group. The group path rides on the session cookie, so like every other
    cookie-authenticated mutation it passes ``same_origin`` (CSRF); the bearer path is not a cookie."""
    if principal.role != "operator":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator role required")
    if principal.via == "group":
        same_origin(request)
    return principal
