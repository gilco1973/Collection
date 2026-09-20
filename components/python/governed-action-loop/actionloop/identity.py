"""Identity library.

The only validator any consumer uses. Tokens are compact HMAC-signed JSON from the fake, or RS256 JWTs from the
bank's provider through `JwksIdP` (the verifier is `jwt_rs256.py`, vendored from rs256-jwt-verify); the issuer allowlist is the authorizer standard every endpoint carries.
The principal chain is Tenant + Human + Agent. Outbound identity is a *reference* bound to audience and
deadline that a handler redeems, never a token it holds (the credential-helper pattern).
"""
from __future__ import annotations
import base64, hashlib, hmac, json, time, uuid
from dataclasses import dataclass, field, asdict


class IdentityError(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeIdP:
    """Stands in for the company IdP (IdentityServer, Auth0, Entra). Issues tokens for humans and agents."""

    def __init__(self, issuer: str, secret: bytes, client_ids: list[str]):
        self.issuer, self._secret, self.client_ids = issuer, secret, list(client_ids)

    def issue(self, sub: str, claims: dict, client_id: str, ttl_s: int = 3600) -> str:
        if client_id not in self.client_ids:
            raise IdentityError("unknown client id")
        body = {"iss": self.issuer, "sub": sub, "aud": client_id, "iat": int(time.time()), "exp": int(time.time()) + ttl_s, **claims}
        raw = _b64(json.dumps(body, sort_keys=True).encode())
        sig = _b64(hmac.new(self._secret, raw.encode(), hashlib.sha256).digest())
        return raw + "." + sig

    def _check(self, token: str) -> dict:
        try:
            raw, sig = token.split(".")
        except ValueError:
            raise IdentityError("malformed token")
        if not hmac.compare_digest(_b64(hmac.new(self._secret, raw.encode(), hashlib.sha256).digest()), sig):
            raise IdentityError("bad signature")
        body = json.loads(_unb64(raw))
        if body.get("exp", 0) < time.time():
            raise IdentityError("expired")
        return body


class JwksIdP:
    """The bank's identity provider: RS256 JWTs verified against its JWKS (signature, exp, nbf, iss, aud).

    Behind the same `_check(token) -> claims` the fake offers, so `IdentityLibrary` does not change. `roles_map`
    turns the directory's `groups` claim into the roles the policy reads (group id -> role); a token without
    groups has no roles. `fetch(url) -> dict` is the consumer's HTTP (the JWKS is cached with a TTL).
    """

    def __init__(self, issuer: str, audiences: tuple, fetch, jwks_url: str | None = None, roles_map: dict | None = None, leeway_s: int = 60, ttl_s: int = 3600):
        from . import jwt_rs256 as J
        self._J, self.issuer, self.audiences, self.roles_map, self.leeway = J, issuer, tuple(audiences), dict(roles_map or {}), leeway_s
        self.jwks = J.Jwks(fetch, jwks_url or J.openid_jwks_url(fetch, issuer.rstrip("/") + "/.well-known/openid-configuration"), ttl_s)

    def _check(self, token: str) -> dict:
        try:
            claims = self._J.verify(token, self.jwks, (self.issuer,), self.audiences, leeway_s=self.leeway)
        except self._J.JwtError as e:
            raise IdentityError(str(e))
        except Exception as e:  # anything the verifier cannot read is not a token
            raise IdentityError(f"unreadable token ({type(e).__name__})")
        roles = [self.roles_map[g] for g in (claims.get("groups") or []) if g in self.roles_map]
        aud = claims.get("aud")
        return {**claims, "aud": aud[0] if isinstance(aud, list) and len(aud) == 1 else aud, "roles": sorted(set(roles + list(claims.get("roles") or []))),
                "name": claims.get("name") or claims.get("preferred_username") or claims.get("sub")}


@dataclass(frozen=True)
class Human:
    id: str
    display: str
    roles: tuple
    jira_account_id: str | None = None
    ado_id: str | None = None


@dataclass(frozen=True)
class Agent:
    principal: str  # e.g. agent:example-coder
    owner: str
    road: str
    ladder: str
    channel: str


@dataclass(frozen=True)
class PrincipalChain:
    tenant: str
    human: Human
    agent: Agent

    def tags(self) -> dict:
        """The claims the policy sees as principal tags."""
        return {"tenant": self.tenant, "human": self.human.id, "roles": list(self.human.roles),
                "jira_account_id": self.human.jira_account_id, "ado_id": self.human.ado_id,
                "agent": self.agent.principal, "ladder": self.agent.ladder, "channel": self.agent.channel, "road": self.agent.road}


class AgentRegistry:
    """Agent principals with a named owner; a change is a reviewed change. Mirror to workload identities in production."""

    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.principal in self._agents:
            raise IdentityError("already registered; change it through a reviewed change")
        self._agents[agent.principal] = agent

    def get(self, principal: str) -> Agent:
        try:
            return self._agents[principal]
        except KeyError:
            raise IdentityError(f"unregistered agent principal {principal}")


@dataclass
class AuthorizerConfig:
    """The JWT authorizer standard: issuer discovery and allowed client ids only."""
    issuer: str
    client_ids: tuple


class IdentityLibrary:
    def __init__(self, idp, authorizer: AuthorizerConfig, registry: AgentRegistry, tenant: str = "company"):
        """`idp` is anything with `_check(token) -> claims`: the fake, or `JwksIdP` for the bank's provider."""
        self.idp, self.authorizer, self.registry, self.tenant = idp, authorizer, registry, tenant
        self._links: dict[str, dict] = {}  # human id -> linked external accounts
        self._references: dict[str, dict] = {}

    # ---- inbound ----
    def link_accounts(self, human_id: str, jira_account_id: str | None = None, ado_id: str | None = None) -> None:
        """Recorded once through consent: the ids the platform matches Jira's assignee field against."""
        self._links[human_id] = {"jira_account_id": jira_account_id, "ado_id": ado_id}

    def resolve(self, token: str, agent_principal: str) -> PrincipalChain:
        """Validate the token against the authorizer standard and resolve Tenant + Human + Agent."""
        body = self.idp._check(token)
        if body["iss"] != self.authorizer.issuer:
            raise IdentityError(f"issuer {body['iss']} is not the company IdP")
        if body["aud"] not in self.authorizer.client_ids:
            raise IdentityError("audience is not a platform client id")
        links = self._links.get(body["sub"], {})
        human = Human(body["sub"], body.get("name", body["sub"]), tuple(body.get("roles", [])), links.get("jira_account_id"), links.get("ado_id"))
        return PrincipalChain(self.tenant, human, self.registry.get(agent_principal))

    # ---- outbound: references, never tokens ----
    def mint_reference(self, chain: PrincipalChain, audience: str, run_id: str, ttl_s: int = 300) -> str:
        ref = "ref_" + uuid.uuid4().hex
        self._references[ref] = {"audience": audience, "run_id": run_id, "human": chain.human.id, "jira": chain.human.jira_account_id, "ado": chain.human.ado_id, "agent": chain.agent.principal, "deadline": time.time() + ttl_s, "redeemed": 0}
        return ref

    def redeem(self, ref: str, audience: str, run_id: str) -> dict:
        r = self._references.get(ref)
        if not r:
            raise IdentityError("unknown reference")
        if r["audience"] != audience or r["run_id"] != run_id:
            raise IdentityError("reference bound to another audience or run")
        if r["deadline"] < time.time():
            raise IdentityError("reference past its deadline")
        r["redeemed"] += 1
        return {"on_behalf_of": r["human"], "on_behalf_of_jira": r["jira"], "on_behalf_of_ado": r["ado"], "agent": r["agent"], "audience": audience}
