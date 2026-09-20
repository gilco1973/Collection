"""``scripts/validate_k8s.py``: the shipped manifests are clean; a root container, a drifting image
tag and a filled-in secret are each named without echoing the secret's value."""

from pathlib import Path

from scripts.validate_k8s import main, validate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
K8S_DIR = PROJECT_ROOT / "deploy" / "k8s"
SHIPPED = (
    "namespace", "configmap", "secret.example", "pvc",
    "deployment", "service", "networkpolicy", "cronjob-retention", "cronjob-index",
)  # fmt: skip

ROOT_DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata: {name: bad, namespace: demo}
spec:
  replicas: 2
  strategy: {type: RollingUpdate}
  selector: {matchLabels: {app: bad}}
  template:
    metadata: {labels: {app: bad}}
    spec:
      containers:
        - name: web
          image: knowledge-base:latest
          ports: [{containerPort: 8765}]
          livenessProbe: {httpGet: {path: /healthz, port: 8765}}
"""
DRIFTING_CRONJOB = """\
apiVersion: batch/v1
kind: CronJob
metadata: {name: bad-purge, namespace: demo}
spec:
  schedule: "0 3 * * *"
  concurrencyPolicy: Allow
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: purge
              image: knowledge-base:0.2.0
              securityContext: {runAsUser: 0, privileged: true}
"""
FILLED_SECRET = """\
apiVersion: v1
kind: Secret
metadata: {name: bad-secrets, namespace: demo}
type: Opaque
stringData:
  KB_API_KEY: "placeholder-value-that-must-never-appear-in-output"
  KB_SESSION_SECRET: ""
"""
EXPECTED_TOKENS = (
    "runAsNonRoot", "runAsUser", "runAsGroup", "fsGroup", "readOnlyRootFilesystem",
    "allowPrivilegeEscalation", "capabilities.drop", "seccompProfile", "automountServiceAccountToken",
    "resources.requests.cpu", "resources.limits.memory", "livenessProbe", "readinessProbe",
    "replicas", "strategy", "concurrencyPolicy", "image tag", "KB_API_KEY",
)  # fmt: skip


def test_shipped_manifests_are_complete_and_clean():
    for stem in SHIPPED:
        assert (K8S_DIR / f"{stem}.yaml").is_file(), stem
    assert validate([K8S_DIR]) == []


def test_root_container_drifting_tag_and_filled_secret_are_named(tmp_path: Path):
    (tmp_path / "bad.yaml").write_text(ROOT_DEPLOYMENT + "---\n" + DRIFTING_CRONJOB + "---\n" + FILLED_SECRET)
    violations = validate([tmp_path])
    text = "\n".join(violations)
    for token in EXPECTED_TOKENS:
        assert token in text, token
    assert "placeholder-value" not in text  # the value itself is never echoed
    assert "KB_SESSION_SECRET" not in text  # an empty value is what the template must hold
    # Every violation names its file; only the cross-container tag comparison spans files.
    assert all(v.startswith("bad.yaml: ") or v.startswith("image tag differs") for v in violations)
    assert "image tag differs across containers: ['0.2.0', 'latest']" in violations


HOST_ACCESS = """\
apiVersion: apps/v1
kind: Deployment
metadata: {name: hosty, namespace: demo}
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector: {matchLabels: {app: hosty}}
  template:
    metadata: {labels: {app: hosty}}
    spec:
      hostNetwork: true
      hostPID: true
      hostIPC: true
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      volumes:
        - {name: docs, hostPath: {path: /srv/docs}}
      containers:
        - name: api
          image: knowledge-base:0.1.0
          ports: [{containerPort: 8765, hostPort: 8765}]
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities: {drop: [ALL], add: [NET_ADMIN]}
          resources: {requests: {cpu: 1, memory: 1Gi}, limits: {cpu: 1, memory: 1Gi}}
          livenessProbe: {httpGet: {path: /api/health, port: 8765}}
          readinessProbe: {httpGet: {path: /api/health/ready, port: 8765}}
"""


def test_host_namespaces_host_paths_host_ports_and_added_capabilities_are_named(tmp_path: Path):
    (tmp_path / "hosty.yaml").write_text(HOST_ACCESS)
    text = "\n".join(validate([tmp_path]))
    for token in ("hostNetwork", "hostPID", "hostIPC", "hostPath", "hostPort", "capabilities.add"):
        assert token in text, token
    clean = HOST_ACCESS.replace("      hostNetwork: true\n      hostPID: true\n      hostIPC: true\n", "")
    clean = clean.replace(
        "        - {name: docs, hostPath: {path: /srv/docs}}\n", "        - {name: docs, emptyDir: {}}\n"
    )
    clean = clean.replace(", hostPort: 8765", "").replace(", add: [NET_ADMIN]", ", add: [NET_BIND_SERVICE]")
    (tmp_path / "hosty.yaml").write_text(clean)
    assert validate([tmp_path]) == []  # NET_BIND_SERVICE is the one addition the restricted profile allows


def test_a_job_that_mounts_the_whole_secret_is_named(tmp_path: Path):
    good = (K8S_DIR / "cronjob-index.yaml").read_text()
    whole_secret = "              envFrom:\n                - secretRef: {name: knowledge-base-secrets}\n"
    wide = good.replace("            - name: KB_EMBED_API_KEY\n", "            - name: KB_EMBED_API_KEY_UNUSED\n")
    wide = wide.replace("              envFrom:\n", whole_secret)
    assert wide != good
    (tmp_path / "cronjob-index.yaml").write_text(wide)
    assert any("secretRef" in v and "envFrom" in v for v in validate([tmp_path]))
    (tmp_path / "cronjob-index.yaml").write_text(good)
    assert validate([tmp_path]) == []


def test_named_probe_port_resolves_and_digest_keeps_its_tag(tmp_path: Path):
    good = (K8S_DIR / "deployment.yaml").read_text()
    pinned = good.replace("image: knowledge-base:0.1.0", "image: knowledge-base:0.1.0@sha256:" + "0" * 64)
    assert pinned != good
    (tmp_path / "deployment.yaml").write_text(pinned)
    assert validate([tmp_path]) == []
    untagged = good.replace("image: knowledge-base:0.1.0", "image: knowledge-base")
    (tmp_path / "deployment.yaml").write_text(untagged)
    assert any("image tag" in v for v in validate([tmp_path]))


def test_empty_directory_and_usage_are_reported(tmp_path: Path, capsys):
    assert validate([tmp_path]) == [f"{tmp_path.name}: no manifests found"]
    assert main([]) == 2
    assert main([str(K8S_DIR)]) == 0
    assert "manifests ok" in capsys.readouterr().out
    (tmp_path / "bad.yaml").write_text(ROOT_DEPLOYMENT)
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "runAsNonRoot" in out and "violation" in out
