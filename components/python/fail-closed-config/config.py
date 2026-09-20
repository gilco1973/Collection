"""Configuration that fails closed.

Everything comes from the environment; nothing has a permissive default in live mode. Secrets are never values here:
they are *names* in the secrets provider. `Settings.validate()` returns every problem at once, `require_valid()` raises,
and `check_config()` is the entrypoint's first command: a live process with a missing gate never listens (exit 2).

Copy this file, keep the three methods, and replace the fields and rules with your service's. The rules below are the
shape Meg uses: mode and environment, a durable store, an https public URL, identity issuers, the access gates, and
one observability target.
"""
from __future__ import annotations
import os, sys
from dataclasses import dataclass, field, fields


class ConfigError(Exception):
    pass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default        # empty means unset, never "an empty gate"


def _list(v: str | None) -> tuple:
    return tuple(x.strip() for x in (v or "").split(",") if x.strip())


@dataclass
class Settings:
    mode: str = "fake"                              # fake | live
    env: str = "sandbox"                            # sandbox | staging | production
    db_path: str = ":memory:"
    public_base_url: str = "http://localhost:8080"
    idp_issuer: str = ""                            # RS256 JWKS discovery
    idp_audience: str = ""
    team_gate_group_ids: tuple = ()                 # who may use the service; empty refuses everyone
    operator_group_id: str = ""                     # who may act; empty refuses everyone
    observability_targets: tuple = ()               # at least one in live mode
    internal_secret_name: str = "app/internal-issuer"   # names, never values
    signing_key_name: str = "app/catalog-signing"
    max_turn_tokens: int = 60000
    prefix: str = field(default="APP_", repr=False)

    @classmethod
    def from_env(cls, prefix: str = "APP_") -> "Settings":
        e = lambda k, d=None: _env(prefix + k, d)
        return cls(mode=e("MODE", "fake"), env=e("ENV", "sandbox"), db_path=e("DB", ":memory:"), public_base_url=e("PUBLIC_URL", "http://localhost:8080"),
                   idp_issuer=e("IDP_ISSUER", ""), idp_audience=e("IDP_AUDIENCE", ""), team_gate_group_ids=_list(e("TEAM_GATE_GROUP_IDS")),
                   operator_group_id=e("OPERATOR_GROUP_ID", ""), observability_targets=_list(e("OBSERVABILITY_TARGETS")),
                   internal_secret_name=e("INTERNAL_SECRET_NAME", "app/internal-issuer"), signing_key_name=e("SIGNING_KEY_NAME", "app/catalog-signing"),
                   max_turn_tokens=int(e("MAX_TURN_TOKENS", "60000")), prefix=prefix)

    def validate(self) -> list[str]:
        """Every problem, named by its environment variable, without its value."""
        p, P = [], self.prefix
        if self.mode not in ("fake", "live"): p.append(f"{P}MODE must be fake or live")
        if self.env not in ("sandbox", "staging", "production"): p.append(f"{P}ENV must be sandbox, staging or production")
        if self.mode == "fake" and self.env == "production": p.append("fake mode is refused in production")
        if not 1000 <= self.max_turn_tokens <= 1_000_000: p.append(f"{P}MAX_TURN_TOKENS out of range")
        if self.mode == "live":
            if self.db_path == ":memory:": p.append(f"{P}DB must be a file path in live mode (the record must survive a restart)")
            if not self.public_base_url.startswith("https://"): p.append(f"{P}PUBLIC_URL must be https in live mode")
            if not self.idp_issuer or not self.idp_audience: p.append(f"{P}IDP_ISSUER and {P}IDP_AUDIENCE are required in live mode")
            if not self.team_gate_group_ids: p.append(f"{P}TEAM_GATE_GROUP_IDS is empty: the team gate would refuse everyone")
            if not self.operator_group_id: p.append(f"{P}OPERATOR_GROUP_ID is empty: the operator gate would refuse everyone")
            if not self.observability_targets: p.append(f"{P}OBSERVABILITY_TARGETS needs at least one target")
        return p

    def require_valid(self) -> "Settings":
        p = self.validate()
        if p:
            raise ConfigError("; ".join(p))
        return self

    def diagnostics(self) -> dict:
        """Presence and shape only, never a value: safe to print at start and in a doctor command."""
        out = {}
        for f in fields(self):
            if f.name == "prefix": continue
            v = getattr(self, f.name)
            out[f.name] = ("unset" if v in ("", (), None) else (f"set ({len(v)} items)" if isinstance(v, tuple) else "set")) if f.name not in ("mode", "env") else v
        return out


def check_config(prefix: str = "APP_", out=sys.stdout) -> int:
    """The entrypoint's first command: exit 0 on `config ok`, 2 with every problem listed."""
    problems = Settings.from_env(prefix).validate()
    if problems:
        for p in problems: print("config:", p, file=out)
        return 2
    print("config ok", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(check_config(os.environ.get("CONFIG_PREFIX", "APP_")))
