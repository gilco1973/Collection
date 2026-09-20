#!/usr/bin/env python3
"""Static invariants of the Kubernetes manifests under ``deploy/k8s`` (no cluster needed).

Every pod spec (Deployment, StatefulSet, Job, CronJob, Pod) runs as the image's non-root user
10001 on a read-only root filesystem, without privilege escalation or capabilities, with the
runtime seccomp profile, no service-account token and explicit resource requests and limits.
The Deployment keeps one replica on the Recreate strategy and probes exactly ``/api/health``
(liveness) and ``/api/health/ready`` (readiness) on port 8765; a CronJob forbids overlapping
runs; every container carries the same image tag; Secret manifests carry keys with empty
values only. Usage: ``python scripts/validate_k8s.py deploy/k8s`` — exit 1 names each violation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

UID = 10001
PORT = 8765
PROBES = {"livenessProbe": "/api/health", "readinessProbe": "/api/health/ready"}
POD_SPEC = {
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
    "Pod": ("spec",),
}


def _dig(node: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def load_documents(paths: list[Path]) -> list[tuple[str, dict]]:
    """Every YAML document with a ``kind`` in the given files (a directory means its *.yaml/*.yml)."""
    documents: list[tuple[str, dict]] = []
    for path in paths:
        files = sorted(p for p in path.iterdir() if p.suffix in {".yaml", ".yml"}) if path.is_dir() else [path]
        for file in files:
            for doc in yaml.safe_load_all(file.read_text(encoding="utf-8")):
                if isinstance(doc, dict) and doc.get("kind"):
                    documents.append((file.name, doc))
    return documents


def image_tag(image: str) -> str | None:
    """``registry/name:tag@sha256:…`` → ``tag``; ``None`` when the reference has no tag."""
    name = image.rsplit("/", 1)[-1].split("@", 1)[0]
    return name.split(":", 1)[1] if ":" in name else None


def _probe_port(container: dict, http: dict) -> Any:
    port = http.get("port")
    if isinstance(port, str):
        for declared in container.get("ports") or []:
            if declared.get("name") == port:
                return declared.get("containerPort")
    return port


def _check_container(where: str, container: dict, pod_sc: dict, kind: str, out: list[str]) -> None:
    sc = container.get("securityContext") or {}
    effective = {**pod_sc, **sc}
    if effective.get("runAsNonRoot") is not True:
        out.append(f"{where}: runAsNonRoot must be true")
    for key in ("runAsUser", "runAsGroup"):
        if effective.get(key) != UID:
            out.append(f"{where}: {key} must be {UID}")
    if sc.get("readOnlyRootFilesystem") is not True:
        out.append(f"{where}: readOnlyRootFilesystem must be true")
    if sc.get("allowPrivilegeEscalation") is not False:
        out.append(f"{where}: allowPrivilegeEscalation must be false")
    if sc.get("privileged"):
        out.append(f"{where}: privileged must not be set")
    if "ALL" not in (_dig(sc, "capabilities", "drop") or []):
        out.append(f"{where}: capabilities.drop must contain ALL")
    added = set(_dig(sc, "capabilities", "add") or []) - {"NET_BIND_SERVICE"}
    if added:
        out.append(f"{where}: capabilities.add must not grant {sorted(added)} (restricted profile)")
    for port in container.get("ports") or []:
        if port.get("hostPort"):
            out.append(f"{where}: hostPort must not be set")
    if kind in ("Job", "CronJob") and any("secretRef" in (src or {}) for src in container.get("envFrom") or []):
        out.append(f"{where}: envFrom.secretRef mounts every secret; a job names the keys it needs via secretKeyRef")
    if _dig(effective, "seccompProfile", "type") != "RuntimeDefault":
        out.append(f"{where}: seccompProfile.type must be RuntimeDefault")
    for section in ("requests", "limits"):
        for resource in ("cpu", "memory"):
            if _dig(container, "resources", section, resource) is None:
                out.append(f"{where}: resources.{section}.{resource} missing")
    if kind != "Deployment":
        return
    for probe, path in PROBES.items():
        http = _dig(container, probe, "httpGet") or {}
        if http.get("path") != path or _probe_port(container, http) != PORT:
            out.append(f"{where}: {probe} must GET {path} on port {PORT}")


def _check_pod(where: str, spec: dict, kind: str, out: list[str], tags: dict[str, str | None]) -> None:
    pod_sc = spec.get("securityContext") or {}
    if spec.get("automountServiceAccountToken") is not False:
        out.append(f"{where}: automountServiceAccountToken must be false")
    if pod_sc.get("fsGroup") != UID:
        out.append(f"{where}: fsGroup must be {UID}")
    for key in ("hostNetwork", "hostPID", "hostIPC"):
        if spec.get(key):
            out.append(f"{where}: {key} must not be true")
    if any("hostPath" in (volume or {}) for volume in spec.get("volumes") or []):
        out.append(f"{where}: hostPath volumes are not allowed")
    containers = list(spec.get("containers") or []) + list(spec.get("initContainers") or [])
    if not containers:
        out.append(f"{where}: no containers")
    for container in containers:
        name = container.get("name", "?")
        tags[f"{where} container {name}"] = image_tag(str(container.get("image", "")))
        _check_container(f"{where} container {name}", container, pod_sc, kind, out)


def _check_secret(where: str, doc: dict, out: list[str]) -> None:
    for field in ("data", "stringData"):
        for key, value in (doc.get(field) or {}).items():
            if value not in (None, ""):
                out.append(f"{where}: {field}.{key} has a value; the template must keep every value empty")


def validate(paths: list[Path]) -> list[str]:
    """Every violation across the manifests at ``paths``; an empty list means clean."""
    out: list[str] = []
    tags: dict[str, str | None] = {}
    documents = load_documents(paths)
    if not documents:
        return [f"{', '.join(p.name for p in paths)}: no manifests found"]
    for file, doc in documents:
        kind = doc["kind"]
        where = f"{file}: {kind}/{_dig(doc, 'metadata', 'name') or '?'}"
        if kind == "Secret":
            _check_secret(where, doc, out)
        if kind == "Deployment":
            if _dig(doc, "spec", "replicas") != 1:
                out.append(f"{where}: replicas must be 1 (the state volume is RWO)")
            if _dig(doc, "spec", "strategy", "type") != "Recreate":
                out.append(f"{where}: strategy.type must be Recreate")
        if kind == "CronJob" and _dig(doc, "spec", "concurrencyPolicy") != "Forbid":
            out.append(f"{where}: concurrencyPolicy must be Forbid")
        if kind in POD_SPEC:
            _check_pod(where, _dig(doc, *POD_SPEC[kind]) or {}, kind, out, tags)
    for where, tag in tags.items():
        if tag is None:
            out.append(f"{where}: image tag missing (a bare or digest-only reference is not pinned to a release)")
    if len({tag for tag in tags.values() if tag is not None}) > 1:
        out.append(f"image tag differs across containers: {sorted({t for t in tags.values() if t})}")
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: validate_k8s.py <manifest-file-or-directory>...", file=sys.stderr)
        return 2
    violations = validate([Path(a) for a in args])
    for violation in violations:
        print(violation)
    if violations:
        print(f"{len(violations)} violation(s)")
        return 1
    print("k8s manifests ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
