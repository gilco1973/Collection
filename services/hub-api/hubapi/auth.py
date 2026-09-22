"""Who is calling: a bearer token resolved to a principal, the authority the hub trusts (specification §4.1).

Two modes. `oidc`: an RS256 JWT from the bank's identity provider, verified against its JWKS (signature, exp, nbf,
iss, aud), then mapped to roles, entitlements, teams and ladder by the identity map, a JSON file the platform team
owns: group id -> what the group grants. `mock`: `mock.<persona>` tokens for the personas in data/examples.json,
for development and demonstrations, refused in production by the settings.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from .vendor import jwt_rs256 as J


class AuthError(Exception):
    def __init__(self, status: int, title: str, detail: str = "", code: str = "unauthenticated"):
        super().__init__(title)
        self.status, self.title, self.detail, self.code = status, title, detail, code


@dataclass
class Principal:
    id: str
    name: str
    email: str
    initials: str
    tenant: str
    roles: list
    ladder: str
    channel: str
    teams: list
    costCentre: str
    entitlements: list
    preferences: dict

    def to_json(self) -> dict:
        return dict(self.__dict__)

    @property
    def handle(self) -> str:
        return self.email.split("@")[0].lower()


DEFAULT_PREFS = {"theme": "system", "accessibility": False, "noAssistant": False, "density": "comfortable", "locale": "en-US", "notifications": {"requests": True, "briefs": True, "digest": False}}
LADDERS = ("L0", "L1", "L2", "L3")


class IdentityMapError(ValueError):
    """The identity map file is not the shape the mapping reads: named at load (and by check-config), never as a 500 per call."""


def _check_grant(where: str, g) -> None:
    """One grant block (`default` or a group): lists of strings, a known ladder, a team with an id."""
    if not isinstance(g, dict): raise IdentityMapError(f"{where} must be an object")
    for k in ("roles", "entitlements"):
        v = g.get(k, [])
        if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v): raise IdentityMapError(f"{where}.{k} must be a list of strings")
    if "ladder" in g and g["ladder"] not in LADDERS: raise IdentityMapError(f"{where}.ladder must be one of {', '.join(LADDERS)}")
    if "costCentre" in g and not isinstance(g["costCentre"], str): raise IdentityMapError(f"{where}.costCentre must be a string")
    if "team" in g and g["team"] is not None and (not isinstance(g["team"], dict) or not isinstance(g["team"].get("id"), str) or not g["team"]["id"]):
        raise IdentityMapError(f"{where}.team must be an object with an id")


class IdentityMap:
    """group id -> grants. `default` applies to every signed-in employee; `groups` add to it; the highest ladder wins.
    The shape is checked here, once: a typo in the file is an IdentityMapError at load, not a 500 on every call."""

    def __init__(self, doc: dict):
        if not isinstance(doc, dict): raise IdentityMapError("the identity map must be a JSON object")
        self.tenant = doc.get("tenant", "t_bank")
        # A key that is present with the wrong type (a list, null) is a typed error, never read as "no grants": a map
        # that silently grants nobody anything would sign every lead in as a plain employee.
        self.default = doc["default"] if "default" in doc else {}
        self.groups = doc["groups"] if "groups" in doc else {}
        self.ai_security_group = doc.get("ai_security_group", "")
        if not isinstance(self.tenant, str) or not isinstance(self.ai_security_group, str): raise IdentityMapError("tenant and ai_security_group must be strings")
        _check_grant("default", self.default)
        if not isinstance(self.groups, dict): raise IdentityMapError("groups must be an object of group id -> grants")
        for gid, g in self.groups.items():
            _check_grant(f"groups[{gid}]", g)

    @classmethod
    def load(cls, path: str) -> "IdentityMap":
        return cls(json.load(open(path, encoding="utf-8")))

    def principal(self, claims: dict, ai_security_group: str = "") -> Principal:
        # A directory that has too many groups to put in the token says so instead of listing them; treating that as
        # "no groups" would sign a lead in as a plain employee. It is refused with the fix named (a groups filter or
        # app roles on the registration), never guessed.
        names = claims.get("_claim_names") or {}
        if "groups" in names or claims.get("hasgroups"):
            raise AuthError(403, "Groups not in the token", "The identity provider left the groups out of this token (too many to list). Ask the identity team to filter the groups claim to the hub's groups, or to emit them as app roles.", "groups.overage")
        raw_groups = claims.get("groups")
        if raw_groups is not None and not isinstance(raw_groups, list):  # a string here would be read as its characters; refuse rather than guess
            raise AuthError(401, "Unauthenticated", "the groups claim must be a list")
        groups = list(dict.fromkeys(g for g in (raw_groups or []) if isinstance(g, str)))  # the token's order, deduplicated: the first group's team is the primary one
        roles, entitlements, teams, ladder, cost = list(self.default.get("roles", [])), list(self.default.get("entitlements", [])), [], self.default.get("ladder", "L0"), self.default.get("costCentre", "")
        for gid in groups:
            g = self.groups.get(gid)
            if not g: continue
            roles += [r for r in g.get("roles", []) if r not in roles]
            entitlements += [e for e in g.get("entitlements", []) if e not in entitlements]
            if g.get("team"): teams.append(dict(g["team"]))
            if g.get("ladder") and LADDERS.index(g["ladder"]) > LADDERS.index(ladder): ladder = g["ladder"]
            if g.get("costCentre"): cost = g["costCentre"]
        if ai_security_group and ai_security_group in groups and "ai.security" not in roles:
            roles.append("ai.security")
        text = lambda k: claims.get(k) if isinstance(claims.get(k), str) else ""   # a claim of another type is not that claim
        # The directory's object id where there is one (stable across app registrations), else the subject; never neither.
        subject = text("oid") or text("sub")
        if not subject.strip(): raise AuthError(401, "Unauthenticated", "token has no subject")
        name = text("name") or text("preferred_username") or text("upn") or text("email") or subject
        email = (text("email") or text("preferred_username") or text("upn")).lower()
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "??"
        return Principal(id="u_" + subject, name=name, email=email, initials=initials, tenant=self.tenant, roles=roles,
                         ladder=ladder, channel="operator", teams=teams, costCentre=cost, entitlements=entitlements, preferences=dict(DEFAULT_PREFS))


class OidcAuth:
    def __init__(self, issuer: str, audience: str, jwks_url: str, fetch, identity_map: IdentityMap, ai_security_group: str, leeway_s: int = 60):
        self.issuer, self.audience, self.map, self.ai_security_group, self.leeway = issuer, audience, identity_map, ai_security_group, leeway_s
        self.jwks = J.Jwks(fetch, jwks_url or J.openid_jwks_url(fetch, issuer.rstrip("/") + "/.well-known/openid-configuration"))

    def ready(self) -> str | None:
        """The identity provider's keys are held and within their maximum age. Stale keys are refreshed through the
        same throttle the verifier uses (one refresh per `min_refresh`, never a fetch per call: anonymous /ready
        cannot make the task hammer the provider), and keys past their refresh time but within their maximum age
        keep serving, so a provider blip degrades this check without turning every task unhealthy."""
        self.jwks.refresh_if_due()
        return None if self.jwks.usable else f"the identity provider's keys are unavailable ({self.jwks.last_error or 'no keys'})"

    def principal(self, token: str) -> Principal:
        try:
            issuers = (self.issuer.rstrip("/"), self.issuer.rstrip("/") + "/")  # providers and operators spell it both ways
            claims = J.verify(token, self.jwks, issuers, (self.audience,), leeway_s=self.leeway)
        except J.JwtError as e:
            raise AuthError(401, "Unauthenticated", str(e))
        except Exception as e:  # the verifier is the authority; anything it cannot read is not a token
            raise AuthError(401, "Unauthenticated", f"unreadable token ({type(e).__name__})")
        try:
            return self.map.principal(claims, self.ai_security_group or self.map.ai_security_group)   # the setting, else the map's own value; the settings refuse a mismatch
        except AuthError:
            raise
        except Exception as e:  # noqa: BLE001 - odd claim types or a map the check missed: a refusal, never a 500 per call
            raise AuthError(401, "Unauthenticated", f"identity map or claims unreadable ({type(e).__name__})")


class MockAuth:
    """`mock.<persona>` from the examples; never in production (the settings refuse it)."""

    def __init__(self, personas: dict):
        self.personas = personas

    def principal(self, token: str) -> Principal:
        if not token.startswith("mock."):
            raise AuthError(401, "Unauthenticated", "mock identity expects a mock.<persona> token")
        p = self.personas.get(token[5:])
        if not p:
            raise AuthError(401, "Unauthenticated", "unknown persona")
        return Principal(**{k: p[k] for k in Principal.__dataclass_fields__})


def bearer(headers) -> str | None:
    auth = headers.get("Authorization", "") or ""
    return auth[7:].strip() if auth.startswith("Bearer ") else None
