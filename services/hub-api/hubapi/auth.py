"""Who is calling: a bearer token resolved to a principal, the authority the hub trusts (specification §4.1).

Two modes. `oidc`: an RS256 JWT from the bank's identity provider, verified against its JWKS (signature, exp, nbf,
iss, aud), then mapped to roles, entitlements, teams and ladder by the identity map, a JSON file the platform team
owns: group id -> what the group grants. `mock`: `mock.<persona>` tokens for the personas in data/examples.json,
for development and demonstrations, refused in production by the settings.
"""
from __future__ import annotations
import json, time
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


class IdentityMap:
    """group id -> grants. `default` applies to every signed-in employee; `groups` add to it; the highest ladder wins."""

    def __init__(self, doc: dict):
        self.tenant = doc.get("tenant", "t_bank")
        self.default = doc.get("default", {})
        self.groups = doc.get("groups", {})
        self.ai_security_group = doc.get("ai_security_group", "")

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
        groups = list(dict.fromkeys(claims.get("groups") or []))  # the token's order, deduplicated: the first group's team is the primary one
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
        name = claims.get("name") or claims.get("preferred_username") or claims.get("upn") or claims.get("email") or claims.get("sub", "")
        email = (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").lower()
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "??"
        # The directory's object id where there is one (stable across app registrations), else the subject.
        return Principal(id="u_" + str(claims.get("oid") or claims.get("sub", "")), name=name, email=email, initials=initials, tenant=self.tenant, roles=roles,
                         ladder=ladder, channel="operator", teams=teams, costCentre=cost, entitlements=entitlements, preferences=dict(DEFAULT_PREFS))


class OidcAuth:
    def __init__(self, issuer: str, audience: str, jwks_url: str, fetch, identity_map: IdentityMap, ai_security_group: str, leeway_s: int = 60):
        self.issuer, self.audience, self.map, self.ai_security_group, self.leeway = issuer, audience, identity_map, ai_security_group, leeway_s
        self.jwks = J.Jwks(fetch, jwks_url or J.openid_jwks_url(fetch, issuer.rstrip("/") + "/.well-known/openid-configuration"))

    def ready(self) -> str | None:
        """The identity provider's keys are cached and fresh, or reachable now; raises when they are not."""
        if self.jwks._keys and time.time() - self.jwks._at < self.jwks.ttl:
            return None
        self.jwks._refresh()
        return None if self.jwks._keys else "the JWKS has no signing keys"

    def principal(self, token: str) -> Principal:
        try:
            claims = J.verify(token, self.jwks, (self.issuer,), (self.audience,), leeway_s=self.leeway)
        except J.JwtError as e:
            raise AuthError(401, "Unauthenticated", str(e))
        except Exception as e:  # the verifier is the authority; anything it cannot read is not a token
            raise AuthError(401, "Unauthenticated", f"unreadable token ({type(e).__name__})")
        return self.map.principal(claims, self.ai_security_group)


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
