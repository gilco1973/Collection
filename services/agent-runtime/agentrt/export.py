"""The chain leaves the task: the audit export as JSON lines with its head, to S3 with SigV4 from the task role.

`audit.export(path)` (the harness's) writes the lines and returns the head; this puts the file under the
configured prefix as `<agent>/<utc date>/<head>.jsonl` and a `latest.json` pointer. A reviewer verifies the
copy with the same `verify()` the harness runs. Standard library only; SigV4 from the aws-sigv4 component.
"""
from __future__ import annotations
import json, os, tempfile, time, urllib.parse
from . import vendor  # noqa: F401
from sigv4 import load_credentials, sign_request


class ExportError(Exception):
    pass


def parse_s3(url: str) -> tuple[str, str]:
    if not url.startswith("s3://"):
        raise ExportError("AUDIT_EXPORT must be s3://bucket/prefix/")
    bucket, _, prefix = url[5:].partition("/")
    if not bucket:
        raise ExportError("AUDIT_EXPORT names no bucket")
    return bucket, prefix.strip("/")


class S3Put:
    """PUT one object with SigV4; the credentials come from the task role at call time."""

    def __init__(self, http, region: str, creds_loader=load_credentials, kms_key_id: str = ""):
        self.http, self.region, self.creds_loader, self.kms_key_id = http, region, creds_loader, kms_key_id

    def put(self, bucket: str, key: str, body: bytes, content_type: str = "application/json") -> str:
        """The object is written encrypted with KMS (the task role's policy allows nothing else); the bucket's key
        unless `kms_key_id` names one."""
        url = f"https://{bucket}.s3.{self.region}.amazonaws.com/{urllib.parse.quote(key)}"
        extra = {"Content-Type": content_type, "x-amz-server-side-encryption": "aws:kms"}
        if self.kms_key_id:
            extra["x-amz-server-side-encryption-aws-kms-key-id"] = self.kms_key_id
        headers = sign_request(self.creds_loader(), "PUT", url, self.region, "s3", extra, body)
        status, _, out = self.http.request("PUT", url, headers, body)
        if status not in (200, 201):
            raise ExportError(f"s3 put {key}: status {status}")
        return f"s3://{bucket}/{key}"


def export_chain(audit, agent_name: str, destination: str, put: S3Put, now: float | None = None, work_dir: str | None = None) -> dict:
    """`work_dir` is where the lines are written before the PUT: the record's volume in the task (the root
    filesystem is read-only there); the system's temporary directory when not given."""
    bucket, prefix = parse_s3(destination)
    with tempfile.TemporaryDirectory(dir=work_dir or None) as d:
        path = os.path.join(d, "chain.jsonl")
        result = audit.export(path)
        body = open(path, "rb").read()
    head = str(result.get("head", "")).replace(":", "-")
    at = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.gmtime(at))
    key = "/".join(x for x in (prefix, agent_name, day, f"{head}.jsonl") if x)
    where = put.put(bucket, key, body, "application/x-ndjson")
    pointer = {"exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)), "head": result.get("head"), "records": result.get("records"), "object": where}
    put.put(bucket, "/".join(x for x in (prefix, agent_name, "latest.json") if x), json.dumps(pointer).encode(), "application/json")
    return pointer
