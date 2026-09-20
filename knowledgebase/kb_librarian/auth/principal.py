"""Who is calling the API: the role, how it was obtained, and how an audit names the caller.

Two ways to be an operator: the shared bearer key (``KB_API_KEY``, break-glass) or a signed-in person
whose ID token listed one of the configured operator groups (the ``operator`` flag in their session,
decided at sign-in). The decision is pure — no request, no app state — so it can be tested on its own;
``api/deps.py`` wires it to requests and supplies the pseudonym key.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from kb_librarian.auth.session import User

PSEUDONYM_HEX = 16


@dataclass(frozen=True)
class Principal:
    """The role, how it was obtained (``key`` = bearer ``KB_API_KEY``, ``group`` = the signed-in person's
    IdP group, ``None`` = a viewer), the signed-in person, if any, and what an audit records as its
    requester: ``key`` for the shared key, ``user:<16 hex>`` for a person — an HMAC of the
    issuer-qualified identity under the server's session secret, so the reports (readable by every
    viewer, exported as files) never carry a subject, name or e-mail and a viewer cannot confirm a
    guessed identity offline; the server log links the pseudonym to the subject for operators."""

    role: str
    via: str | None
    user: User | None
    requested_by: str | None = None


def pseudonym(user: User, key: bytes) -> str:
    return "user:" + hmac.new(key, user.storage_key.encode("utf-8"), hashlib.sha256).hexdigest()[:PSEUDONYM_HEX]


def principal_for(
    operator_key: str | None, bearer: str | None, user: User | None, key: bytes | None = None
) -> Principal:
    """The bearer key is checked first (break-glass, whoever is signed in); then the session's flag.
    ``key`` (the session secret) is needed only for a group operator, who cannot exist without one."""
    if operator_key and bearer and secrets.compare_digest(bearer.encode(), operator_key.encode()):
        return Principal("operator", "key", user, "key")
    if user is not None and user.operator:
        if key is None:
            raise RuntimeError("a group operator needs the session secret for its pseudonym")
        return Principal("operator", "group", user, pseudonym(user, key))
    return Principal("viewer", None, user)
