"""The chain leaves the task: the audit export as JSON lines with its head, to S3 with SigV4 from the task role.

`audit.export(path)` (the harness's) writes the lines and returns the head; this puts the file under the
configured prefix as `<agent>/<utc date>/<head>.jsonl` and a `latest.json` pointer. The pointer only ever moves
forward: it is read first, and an export whose chain is shorter than the last one, or does not carry the last
head, is refused (a record restored from an old backup never hides the longer export). A reviewer verifies the
copy with the same `verify()` the harness runs. Standard library only; SigV4 from the aws-sigv4 component.
"""
from __future__ import annotations
import hashlib, json, os, tempfile, time, urllib.parse
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
    """PUT one object (and GET the pointer back) with SigV4; the credentials come from the task role at call time."""

    def __init__(self, http, region: str, creds_loader=load_credentials, kms_key_id: str = ""):
        self.http, self.region, self.creds_loader, self.kms_key_id = http, region, creds_loader, kms_key_id

    def _url(self, bucket: str, key: str) -> str:
        return f"https://{bucket}.s3.{self.region}.amazonaws.com/{urllib.parse.quote(key)}"

    def get(self, bucket: str, key: str) -> bytes | None:
        """The object's bytes, or None when there is no such object (404). Any other failure is named."""
        url = self._url(bucket, key)
        headers = sign_request(self.creds_loader(), "GET", url, self.region, "s3", {}, b"")
        status, _, out = self.http.request("GET", url, headers, b"")
        if status == 404:
            return None
        if status != 200:
            raise ExportError(f"s3 get {key}: status {status}")
        return out

    def put(self, bucket: str, key: str, body: bytes, content_type: str = "application/json") -> str:
        """The object is written encrypted with KMS (the task role's policy allows nothing else); the bucket's key
        unless `kms_key_id` names one."""
        url = self._url(bucket, key)
        extra = {"Content-Type": content_type, "x-amz-server-side-encryption": "aws:kms"}
        if self.kms_key_id:
            extra["x-amz-server-side-encryption-aws-kms-key-id"] = self.kms_key_id
        headers = sign_request(self.creds_loader(), "PUT", url, self.region, "s3", extra, body)
        status, _, out = self.http.request("PUT", url, headers, body)
        if status not in (200, 201):
            raise ExportError(f"s3 put {key}: status {status}")
        return f"s3://{bucket}/{key}"


def last_pointer(put, bucket: str, key: str) -> dict | None:
    """The pointer of the last export, or None when there was none: no object (404), an empty object, or a `put`
    that cannot read (a fake without `get`). A pointer that is there but unreadable is an error, not "none"."""
    get = getattr(put, "get", None)
    if get is None:
        return None
    raw = get(bucket, key)
    if not raw:
        return None
    try:
        p = json.loads(raw)
    except ValueError:
        raise ExportError(f"the last export's pointer {key} is not JSON")
    if not isinstance(p, dict):
        raise ExportError(f"the last export's pointer {key} is not an object")
    return p


def export_chain(audit, agent_name: str, destination: str, put: S3Put, now: float | None = None, work_dir: str | None = None) -> dict:
    """`work_dir` is where the lines are written before the PUT: the record's volume in the task (the root
    filesystem is read-only there); the system's temporary directory when not given. The pointer is read before
    anything is written: a chain shorter than the last export, or one the last head is not on, is refused."""
    bucket, prefix = parse_s3(destination)
    pointer_key = "/".join(x for x in (prefix, agent_name, "latest.json") if x)
    previous = last_pointer(put, bucket, pointer_key)
    with tempfile.TemporaryDirectory(dir=work_dir or None) as d:
        path = os.path.join(d, "chain.jsonl")
        result = audit.export(path)
        body = open(path, "rb").read()
    if previous:
        last_records, last_head = previous.get("records") or 0, previous.get("head")
        if int(result.get("records") or 0) < int(last_records):
            raise ExportError(f"chain shorter than the last export: {result.get('records')} records, the last export had {last_records}")
        hashes = {"sha256:" + hashlib.sha256(line).hexdigest() for line in body.split(b"\n") if line}
        if last_head and last_head not in hashes:
            raise ExportError(f"chain shorter than the last export: its head {last_head} is not on this chain")
    head = str(result.get("head", "")).replace(":", "-")
    at = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.gmtime(at))
    key = "/".join(x for x in (prefix, agent_name, day, f"{head}.jsonl") if x)
    where = put.put(bucket, key, body, "application/x-ndjson")
    pointer = {"exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)), "head": result.get("head"), "records": result.get("records"), "object": where,
               "previous": previous.get("head") if previous else None}
    put.put(bucket, pointer_key, json.dumps(pointer).encode(), "application/json")
    return pointer
