"""Configuration that fails closed, for the agent runtime (AGENT_ prefix).

Fakes exist for the sandbox: a fake identity provider, a local signing key, the rules engine and fake targets.
Staging and production refuse every one of them and require the bank's provider, KMS, Bedrock behind the VPC
endpoint, real targets for every target the template names, a file-backed record and a non-environment secrets
provider. Problems are named by variable, never by value.
"""
from __future__ import annotations
import os, sys
from dataclasses import dataclass, field, fields

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE = os.path.dirname(HERE)
KNOWN_AGENTS = ("incident-first-read-agent",)
CONNECTORS = ("tickets", "deploys")     # the targets this runtime has a connector for (jira-connector, ado-connector)


def template_targets(name: str) -> tuple:
    """The targets the agent's template names, read from the vendored TEMPLATE.md: never a table to keep in step."""
    import json as _json, re as _re
    path = os.path.join(HERE, "vendor", "TEMPLATE.md")
    try:
        block = _re.search(r"```json\n(.*?)\n```", open(path, encoding="utf-8").read(), _re.S)
        tools = _json.loads(block.group(1))["tools"] if block else []
    except (OSError, ValueError, KeyError):
        return ()
    return tuple(dict.fromkeys(t["target"] for t in tools if isinstance(t, dict) and t.get("target")))


class ConfigError(Exception):
    pass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _list(v: str | None) -> tuple:
    return tuple(x.strip() for x in (v or "").split(",") if x.strip())


def _map(v: str | None) -> dict:
    out = {}
    for item in _list(v):
        k, _, val = item.partition("=")
        if k and val: out[k.strip()] = val.strip()
    return out


@dataclass
class Settings:
    env: str = "sandbox"
    name: str = "incident-first-read-agent"
    listen_host: str = "127.0.0.1"
    listen_port: int = 8081
    public_url: str = "http://localhost:8081/mcp"
    db_path: str = ":memory:"
    identity: str = "fake"                         # fake | oidc
    idp_issuer: str = ""
    idp_audience: str = ""
    idp_jwks_url: str = ""
    operator_group_id: str = ""                    # directory group -> the operator role
    approver_group_id: str = ""                    # directory group -> the approver role (W2)
    signing: str = "local"                         # local | kms
    kms_key_id: str = ""
    engine: str = "rules"                          # rules | bedrock
    bedrock_region: str = ""
    bedrock_endpoint: str = ""
    bedrock_model_id: str = ""
    bedrock_inference_profile_arn: str = ""
    bedrock_max_output_tokens: int = 1500
    targets: tuple = ()                            # which of the template's targets are real systems; the rest are fakes (sandbox only)
    jira_url: str = ""
    jira_token_name: str = "agents/jira-token"
    jira_user: str = ""
    jira_auth: str = "basic"
    deploys_url: str = ""
    deploys_project: str = ""
    deploys_pat_name: str = "agents/ado-pat"
    deploys_pipelines: dict = field(default_factory=dict)   # service=pipeline id
    audit_export: str = ""                         # s3://bucket/prefix/ or empty
    audit_export_interval_s: int = 0               # export the chain from inside the task every N seconds; 0 leaves it to a scheduled task
    secrets: str = "env"
    max_body_bytes: int = 1_000_000
    runs_per_minute: int = 60                      # runs and confirmations per person per minute (a token bucket); 0 disables
    log_level: str = "INFO"
    build_sha: str = "dev"
    prefix: str = field(default="AGENT_", repr=False)

    @classmethod
    def from_env(cls, prefix: str = "AGENT_") -> "Settings":
        e = lambda k, d=None: _env(prefix + k, d)
        d = cls()
        return cls(env=e("ENV", d.env), name=e("NAME", d.name), listen_host=e("LISTEN_HOST", d.listen_host), listen_port=int(e("LISTEN_PORT", str(d.listen_port))),
                   public_url=e("PUBLIC_URL", d.public_url), db_path=e("DB", d.db_path), identity=e("IDENTITY", d.identity), idp_issuer=e("IDP_ISSUER", ""), idp_audience=e("IDP_AUDIENCE", ""),
                   idp_jwks_url=e("IDP_JWKS_URL", ""), operator_group_id=e("OPERATOR_GROUP_ID", ""), approver_group_id=e("APPROVER_GROUP_ID", ""), signing=e("SIGNING", d.signing),
                   kms_key_id=e("KMS_KEY_ID", ""), engine=e("ENGINE", d.engine), bedrock_region=e("BEDROCK_REGION", e("AWS_REGION", "") or ""), bedrock_endpoint=e("BEDROCK_ENDPOINT", ""),
                   bedrock_model_id=e("BEDROCK_MODEL_ID", ""), bedrock_inference_profile_arn=e("BEDROCK_INFERENCE_PROFILE_ARN", ""), bedrock_max_output_tokens=int(e("BEDROCK_MAX_OUTPUT_TOKENS", "1500")),
                   targets=_list(e("TARGETS")), jira_url=e("JIRA_URL", ""), jira_token_name=e("JIRA_TOKEN_NAME", d.jira_token_name), jira_user=e("JIRA_USER", ""), jira_auth=e("JIRA_AUTH", "basic"),
                   deploys_url=e("DEPLOYS_URL", ""), deploys_project=e("DEPLOYS_PROJECT", ""), deploys_pat_name=e("DEPLOYS_PAT_NAME", d.deploys_pat_name), deploys_pipelines=_map(e("DEPLOYS_PIPELINES")),
                   audit_export=e("AUDIT_EXPORT", ""), audit_export_interval_s=int(e("AUDIT_EXPORT_INTERVAL_S", "0")), secrets=e("SECRETS", d.secrets),
                   max_body_bytes=int(e("MAX_BODY_BYTES", str(d.max_body_bytes))), runs_per_minute=int(e("RUNS_PER_MINUTE", str(d.runs_per_minute))),
                   log_level=e("LOG_LEVEL", d.log_level), build_sha=e("BUILD_SHA", d.build_sha), prefix=prefix)

    @property
    def live(self) -> bool:
        return self.env in ("staging", "production")

    def validate(self) -> list[str]:
        p, P = [], self.prefix
        if self.env not in ("sandbox", "staging", "production"): p.append(f"{P}ENV must be sandbox, staging or production")
        if self.name not in KNOWN_AGENTS: p.append(f"{P}NAME must be one of {KNOWN_AGENTS}")
        if self.identity not in ("fake", "oidc"): p.append(f"{P}IDENTITY must be fake or oidc")
        if self.signing not in ("local", "kms"): p.append(f"{P}SIGNING must be local or kms")
        if self.engine not in ("rules", "bedrock"): p.append(f"{P}ENGINE must be rules or bedrock")
        if not 1 <= self.listen_port <= 65535: p.append(f"{P}LISTEN_PORT out of range")
        named = template_targets(self.name)
        unknown = [t for t in self.targets if t not in named]
        if unknown: p.append(f"{P}TARGETS names targets the template does not: {', '.join(unknown)}")
        without = [t for t in named if t not in CONNECTORS]
        if without: p.append(f"the template names targets this runtime has no connector for: {', '.join(without)}")
        if not 10_000 <= self.max_body_bytes <= 50_000_000: p.append(f"{P}MAX_BODY_BYTES out of range")
        if self.identity == "oidc":
            if not self.idp_issuer or not self.idp_audience: p.append(f"{P}IDP_ISSUER and {P}IDP_AUDIENCE are required with oidc")
            if self.idp_issuer and not self.idp_issuer.startswith("https://"): p.append(f"{P}IDP_ISSUER must be https")
            if not self.operator_group_id: p.append(f"{P}OPERATOR_GROUP_ID is empty: nobody could act through the agent")
        if self.signing == "kms" and not self.kms_key_id: p.append(f"{P}KMS_KEY_ID is required with kms signing")
        if self.engine == "bedrock":
            if not self.bedrock_region: p.append(f"{P}BEDROCK_REGION (or AWS_REGION) is required with the bedrock engine")
            if not (self.bedrock_model_id or self.bedrock_inference_profile_arn): p.append(f"{P}BEDROCK_MODEL_ID or {P}BEDROCK_INFERENCE_PROFILE_ARN is required with the bedrock engine")
        if "tickets" in self.targets and not self.jira_url: p.append(f"{P}JIRA_URL is required when tickets is a real target")
        if "deploys" in self.targets and not (self.deploys_url and self.deploys_project and self.deploys_pipelines): p.append(f"{P}DEPLOYS_URL, {P}DEPLOYS_PROJECT and {P}DEPLOYS_PIPELINES are required when deploys is a real target")
        if self.audit_export and not self.audit_export.startswith("s3://"): p.append(f"{P}AUDIT_EXPORT must be s3://bucket/prefix/ or empty")
        if self.audit_export_interval_s and not self.audit_export: p.append(f"{P}AUDIT_EXPORT_INTERVAL_S needs {P}AUDIT_EXPORT")
        if not 0 <= self.audit_export_interval_s <= 7 * 86_400: p.append(f"{P}AUDIT_EXPORT_INTERVAL_S out of range (0, or up to 7 days)")
        if not 0 <= self.runs_per_minute <= 10_000: p.append(f"{P}RUNS_PER_MINUTE out of range")
        if self.live and self.runs_per_minute == 0: p.append(f"{P}RUNS_PER_MINUTE must be above 0 in staging and production")
        if self.live:
            if self.identity == "fake": p.append("the fake identity provider is refused in staging and production")
            if self.signing == "local": p.append("local signing is refused in staging and production; use kms")
            if self.engine == "rules": p.append("the rules engine is refused in staging and production; use bedrock")
            missing = [t for t in named if t not in self.targets]
            if missing: p.append(f"{P}TARGETS must name a real system for every target the template names; fakes are refused for: {', '.join(missing)}")
            if self.db_path == ":memory:": p.append(f"{P}DB must be a file path in staging and production")
            if not self.public_url.startswith("https://"): p.append(f"{P}PUBLIC_URL must be https in staging and production")
            if self.engine == "bedrock" and not self.bedrock_endpoint: p.append(f"{P}BEDROCK_ENDPOINT (the bank's VPC endpoint) is required in staging and production")
            if self.secrets == "env": p.append(f"{P}SECRETS must be aws or file:<path> in staging and production")
        if self.env == "production" and not self.audit_export: p.append(f"{P}AUDIT_EXPORT is required in production: the chain must leave the task")
        if not (self.secrets in ("env", "aws") or self.secrets.startswith("file:")): p.append(f"{P}SECRETS must be env, aws or file:<path>")
        return p

    def require_valid(self) -> "Settings":
        p = self.validate()
        if p:
            raise ConfigError("; ".join(p))
        return self

    def diagnostics(self) -> dict:
        out = {}
        for f in fields(self):
            if f.name == "prefix": continue
            v = getattr(self, f.name)
            out[f.name] = v if f.name in ("env", "name", "identity", "signing", "engine", "secrets", "log_level", "listen_port") else ("unset" if v in ("", (), {}, None) else "set")
        return out


def check_config(prefix: str = "AGENT_", out=sys.stdout) -> int:
    problems = Settings.from_env(prefix).validate()
    if problems:
        for p in problems: print("config:", p, file=out)
        return 2
    print("config ok", file=out)
    return 0
