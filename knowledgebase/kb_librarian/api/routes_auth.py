"""Sign-in routes: ``/auth/login`` → IdP → ``/auth/callback`` → session cookie; ``/auth/logout``;
``/auth/logout-everywhere`` (revokes every session of the reader through their session epoch).

The login transaction (state, nonce, PKCE verifier, return path) travels in a short-lived signed
cookie, so the server stays stateless and a callback can only complete the request that started
in the same browser. Both cookies are HttpOnly, SameSite=Lax, Path=/ and carry ``Secure`` whenever
the console is served over https (``settings.cookies_secure``, decided from the configured redirect
URI so a proxy that drops X-Forwarded-Proto cannot downgrade it). Error responses are fixed
strings; the detail is logged server-side. The operator role is decided here, once, from the ID
token's group claim: it lives in the session, so a change at the IdP applies at the next sign-in.
"""

import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from kb_librarian.api.deps import AppState, get_state, require_user, same_origin
from kb_librarian.auth.oidc import OidcError, pkce_pair
from kb_librarian.auth.session import (
    LOGIN_COOKIE,
    LOGIN_TTL_S,
    MAX_CLAIM_CHARS,
    MAX_SUB_CHARS,
    SESSION_COOKIE,
    User,
    safe_return_path,
    sign,
    verify,
)

router = APIRouter()
log = logging.getLogger(__name__)
_EXPIRED = "login request expired or did not start in this browser; try again"
_DECLINED = "the identity provider declined the sign-in"
_UNVERIFIED = "the sign-in could not be verified"
_UNAVAILABLE = "the identity provider is unavailable"


def _cookie(response: Response, state: AppState, name: str, value: str | None, max_age: int) -> None:
    secure = state.settings.cookies_secure
    if value is None:
        response.delete_cookie(name, path="/", httponly=True, samesite="lax", secure=secure)
    else:
        response.set_cookie(name, value, max_age=max_age, path="/", httponly=True, samesite="lax", secure=secure)


def _provider(state: AppState):
    provider = state.oidc()
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "single sign-on is not configured on this server")
    return provider


@router.get("/auth/login", include_in_schema=False)
def login(next: str | None = None, state: AppState = Depends(get_state)) -> Response:
    provider = _provider(state)
    tx_state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    try:
        url = provider.authorization_url(tx_state, nonce, challenge)
    except OidcError as exc:
        log.warning("sign-in could not start: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, _UNAVAILABLE) from exc
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    payload = {"state": tx_state, "nonce": nonce, "verifier": verifier, "next": safe_return_path(next)}
    _cookie(response, state, LOGIN_COOKIE, sign(payload, state.session_secret, LOGIN_TTL_S, "login"), LOGIN_TTL_S)
    return response


def _state_matches(returned: str | None, expected: object) -> bool:
    try:
        return bool(returned) and hmac.compare_digest(str(returned).encode("utf-8"), str(expected).encode("utf-8"))
    except UnicodeError:
        return False


def _is_operator(groups: object, operator_groups: frozenset[str]) -> bool:
    """Only a list of strings counts as a group claim; any other shape (or a mixed list) grants nothing."""
    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
        return False
    return bool(operator_groups.intersection(groups))


@router.get("/auth/callback", include_in_schema=False)
def callback(request: Request, state: AppState = Depends(get_state)) -> Response:
    provider = _provider(state)
    tx = verify(request.cookies.get(LOGIN_COOKIE), state.session_secret, "login")
    if tx is None or not _state_matches(request.query_params.get("state"), tx.get("state", "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _EXPIRED)
    code, error = request.query_params.get("code"), request.query_params.get("error")
    if error or not code:
        log.info("sign-in declined by the identity provider: %s", (error or "no code")[:80])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _DECLINED)
    try:
        tokens = provider.exchange_code(code, str(tx.get("verifier", "")))
        claims = provider.verify_id_token(tokens["id_token"], str(tx.get("nonce", "")))
    except OidcError as exc:
        log.warning("sign-in rejected: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _UNVERIFIED) from exc
    sub = str(claims.get("sub", ""))
    if not sub or len(sub) > MAX_SUB_CHARS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _UNVERIFIED)
    email = claims.get("email")
    user = User(
        sub=sub,
        iss=provider.issuer,
        name=str(claims.get("name") or claims.get("preferred_username") or email or sub)[:MAX_CLAIM_CHARS],
        email=email[:MAX_CLAIM_CHARS] if isinstance(email, str) else None,
        operator=_is_operator(claims.get(state.settings.oidc_groups_claim), state.settings.operator_groups),
    )
    # The epoch the reader's record holds now: "sign out everywhere" moves it and every earlier cookie dies.
    session = {**user.as_dict(), "iss": user.iss, "epoch": state.profiles.session_epoch(user.storage_key)}
    response = RedirectResponse(safe_return_path(str(tx.get("next") or "/")), status_code=status.HTTP_302_FOUND)
    ttl = state.settings.session_ttl_hours * 3600
    _cookie(response, state, SESSION_COOKIE, sign(session, state.session_secret, ttl, "session"), ttl)
    _cookie(response, state, LOGIN_COOKIE, None, 0)
    return response


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(same_origin)])
def logout(state: AppState = Depends(get_state)) -> Response:
    """Drop the session cookie. Same-origin only: a cross-site form must not be able to sign a reader out."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _cookie(response, state, SESSION_COOKIE, None, 0)
    return response


@router.post("/auth/logout-everywhere", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(user: User = Depends(require_user), state: AppState = Depends(get_state)) -> Response:
    """Revoke every session of the signed-in reader (their epoch moves), then drop this browser's cookie.
    ``require_user`` brings the same-origin guard: a foreign site cannot sign a reader out of everything."""
    state.profiles.bump_session_epoch(user.storage_key)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _cookie(response, state, SESSION_COOKIE, None, 0)
    return response
