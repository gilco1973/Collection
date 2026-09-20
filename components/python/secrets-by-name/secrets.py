"""The secrets provider: a handler never holds a credential; it asks the provider for a named
secret at call time, and the provider is AWS Secrets Manager in production, a JSON file in a sandbox, or the
environment (`<PREFIX>SECRET_<NAME>`) in tests. Values are cached for a short time and never logged.
"""
from __future__ import annotations
import json, os, time


class SecretError(Exception):
    pass


class EnvSecrets:
    def __init__(self, prefix: str = "APP_"):
        self.prefix = prefix

    def get(self, name: str) -> str:
        v = os.environ.get(self.prefix + "SECRET_" + name.upper().replace("/", "_").replace("-", "_"))
        if v is None:
            raise SecretError(f"secret {name} is not set")
        return v


class FileSecrets:
    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            self._d = json.load(f)

    def get(self, name: str) -> str:
        if name not in self._d:
            raise SecretError(f"secret {name} is not in the file")
        return self._d[name]


class DictSecrets:
    def __init__(self, d: dict):
        self._d = dict(d)

    def get(self, name: str) -> str:
        if name not in self._d:
            raise SecretError(f"secret {name} is not provided")
        return self._d[name]


class SecretsManager:
    def __init__(self, aws, ttl_s: int = 300):
        self.aws, self.ttl, self._cache = aws, ttl_s, {}

    def get(self, name: str) -> str:
        c = self._cache.get(name)
        if c and c[0] > time.time():
            return c[1]
        r = self.aws.call("secretsmanager", "secretsmanager", "secretsmanager.GetSecretValue", {"SecretId": name})
        if "SecretString" not in r:
            raise SecretError(f"secret {name} has no string value")
        self._cache[name] = (time.time() + self.ttl, r["SecretString"])
        return r["SecretString"]


def provider_from_env(aws_factory=None, prefix: str = "APP_"):
    """`<PREFIX>SECRETS` selects the provider: env (default), file:<path>, or aws."""
    src = os.environ.get(prefix + "SECRETS", "env")
    if src == "env":
        return EnvSecrets(prefix)
    if src.startswith("file:"):
        return FileSecrets(src[5:])
    if src == "aws":
        if aws_factory is None:
            raise SecretError("aws secrets need an AwsJson factory")
        return SecretsManager(aws_factory())
    raise SecretError(f"unknown {prefix}SECRETS {src}")


class UpstreamError(Exception):
    pass


def require_credential(credential: dict, audience: str) -> str:
    """A handler refuses to run without a redeemed reference for its own audience (see governed-action-loop)."""
    if not credential or credential.get("audience") != audience or not credential.get("on_behalf_of"):
        raise UpstreamError(f"{audience}: no redeemed credential for this audience")
    return credential["on_behalf_of"]
