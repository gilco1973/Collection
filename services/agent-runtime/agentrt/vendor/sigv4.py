"""AWS Signature Version 4 with the standard library (for CloudWatch, Secrets Manager and ECS calls).

Credentials come from the task role (container credentials endpoint), the instance role, or the environment,
in that order. No SDK: hmac + hashlib. The signing steps follow the published algorithm; the test suite checks
the canonical request against the AWS documentation's worked example.
"""
from __future__ import annotations
import datetime as _dt, hashlib, hmac, json, os, urllib.parse, urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Credentials:
    access_key: str
    secret_key: str
    session_token: str | None = None


def load_credentials(http_get=None) -> Credentials:
    """Task role first (ECS), then the environment. Never a file with long-lived keys in production."""
    rel = os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
    full = os.environ.get("AWS_CONTAINER_CREDENTIALS_FULL_URI")
    url = ("http://169.254.170.2" + rel) if rel else full
    if url:
        get = http_get or (lambda u: urllib.request.urlopen(u, timeout=2).read())
        j = json.loads(get(url))
        return Credentials(j["AccessKeyId"], j["SecretAccessKey"], j.get("Token"))
    ak, sk = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not ak or not sk:
        raise RuntimeError("no AWS credentials: task role or environment")
    return Credentials(ak, sk, os.environ.get("AWS_SESSION_TOKEN"))


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    k = _sign(("AWS4" + secret).encode(), date)
    k = _sign(k, region); k = _sign(k, service)
    return _sign(k, "aws4_request")


def canonical_query(query: dict) -> str:
    return "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}" for k, v in sorted(query.items()))


def sign_request(creds: Credentials, method: str, url: str, region: str, service: str, headers: dict, body: bytes, now: _dt.datetime | None = None) -> dict:
    """Return the headers with Authorization, X-Amz-Date (and the session token) added."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ"); date = now.strftime("%Y%m%d")
    p = urllib.parse.urlsplit(url)
    host = p.netloc
    h = {k.lower(): " ".join(v.split()) for k, v in headers.items()}
    h["host"] = host; h["x-amz-date"] = amz_date
    if creds.session_token:
        h["x-amz-security-token"] = creds.session_token
    payload_hash = hashlib.sha256(body or b"").hexdigest()
    h["x-amz-content-sha256"] = payload_hash
    signed = ";".join(sorted(h))
    canonical_headers = "".join(f"{k}:{h[k]}\n" for k in sorted(h))
    q = dict(urllib.parse.parse_qsl(p.query, keep_blank_values=True))
    canonical = "\n".join([method, urllib.parse.quote(p.path or "/", safe="/-_.~"), canonical_query(q), canonical_headers, signed, payload_hash])
    scope = f"{date}/{region}/{service}/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    sig = hmac.new(signing_key(creds.secret_key, date, region, service), sts.encode(), hashlib.sha256).hexdigest()
    out = {k: v for k, v in headers.items()}
    out["X-Amz-Date"] = amz_date; out["X-Amz-Content-Sha256"] = payload_hash
    if creds.session_token:
        out["X-Amz-Security-Token"] = creds.session_token
    out["Authorization"] = f"AWS4-HMAC-SHA256 Credential={creds.access_key}/{scope}, SignedHeaders={signed}, Signature={sig}"
    return out


class AwsJson:
    """A JSON-protocol AWS call (CloudWatch Logs, ECS, Secrets Manager) signed per request."""

    def __init__(self, http, region: str, creds_loader=load_credentials):
        self.http, self.region, self._creds_loader, self._creds = http, region, creds_loader, None

    def creds(self) -> Credentials:
        if self._creds is None:
            self._creds = self._creds_loader()
        return self._creds

    def call(self, service: str, endpoint_prefix: str, target: str, payload: dict, content_type: str = "application/x-amz-json-1.1") -> dict:
        url = f"https://{endpoint_prefix}.{self.region}.amazonaws.com/"
        body = json.dumps(payload).encode()
        headers = sign_request(self.creds(), "POST", url, self.region, service, {"Content-Type": content_type, "X-Amz-Target": target}, body)
        _, _, data = self.http.request("POST", url, headers, body)
        return json.loads(data) if data else {}

    def query(self, service: str, endpoint_prefix: str, params: dict) -> bytes:
        """The query protocol (CloudWatch metrics): form-encoded body, XML back."""
        url = f"https://{endpoint_prefix}.{self.region}.amazonaws.com/"
        body = urllib.parse.urlencode(sorted(params.items())).encode()
        headers = sign_request(self.creds(), "POST", url, self.region, service, {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}, body)
        _, _, data = self.http.request("POST", url, headers, body)
        return data
