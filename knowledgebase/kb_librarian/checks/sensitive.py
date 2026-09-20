"""Sensitive-content scan over every page and YAML catalog, frontmatter included.

Messages never echo a matched value, only its category and location. ``redact``
applies the same patterns to any text that is about to be persisted.
"""

import re
from pathlib import Path

from kb_librarian.catalog.catalog import Catalog
from kb_librarian.checks.base import Finding
from kb_librarian.kbconfig import KbConfig

CHECK = "sensitive"
ALLOW_MARKER = "<!-- kb-allow-sensitive -->"
_PLACEHOLDER = re.compile(r"EXAMPLE|PLACEHOLDER|CHANGEME|REDACTED", re.I)
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "critical"),
    ("anthropic api key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), "critical"),
    ("openai/stripe style key", re.compile(r"\bsk[-_](?:live|test|proj)?[-_]?[A-Za-z0-9]{20,}\b"), "critical"),
    (
        "github token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        "critical",
    ),
    ("slack token", re.compile(r"\bxox[abpers]-[A-Za-z0-9-]{10,}\b"), "critical"),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "critical"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), "critical"),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "critical"),
    ("atlassian api token", re.compile(r"\bATATT3[A-Za-z0-9_\-]{20,}\b"), "critical"),
    ("connection string with password", re.compile(r"\b[a-z][a-z0-9+]*://[^\s/:@]+:[^\s/@]+@[^\s]+"), "critical"),
    ("azure account key", re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}"), "critical"),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_\.]{20,}(?=\s|$)"), "critical"),
    ("basic auth credential", re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/]{16,}={0,2}(?=\s|$)"), "critical"),
    (
        "secret assignment",
        re.compile(
            r"(?i)[\"']?\b(password|passwd|secret|api[_-]?key|access[_-]?key|token)[\"']?\s*[:=]\s*[\"']?(?P<value>[^\s\"',]{8,})"
        ),
        "error",
    ),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b"), "error"),
    ("card number candidate", re.compile(r"\b(?:\d[ -]?){15,16}\b"), "error"),
    ("email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "warning"),
    ("ipv4 address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "warning"),
]


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == parity:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _iban_ok(candidate: str) -> bool:
    compact = re.sub(r"\s", "", candidate)
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def _confirmed(label: str, match: re.Match) -> bool:
    text = match.group(0)
    if label == "card number candidate":
        return _luhn_ok(re.sub(r"\D", "", text))
    if label == "iban":
        return _iban_ok(text)
    if label == "secret assignment":
        value = match.group("value")
        if value.startswith(("$", "{", "<", "os.environ", "process.env", "env(", "getenv")) or "(" in value:
            return False  # a reference to a secret, not a secret
        return not _ENV_NAME.match(value) and not _PLACEHOLDER.search(value)
    if label == "email address":
        return not text.lower().endswith("@example.com")
    return True


WITHHOLD_SEVERITIES = frozenset({"critical", "error"})  # a bank withholds on card numbers and IBANs too


def withholds(lines: list[str], path: str) -> bool:
    """The one rule for keeping content away from readers, shared by pages, catalogs and search."""
    return any(f.severity in WITHHOLD_SEVERITIES for f in scan_lines(lines, path))


def scan_lines(lines: list[str], path: str, offset: int = 0) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(lines, start=1 + offset):
        allowlisted = ALLOW_MARKER in line
        for label, pattern, severity in _PATTERNS:
            match = pattern.search(line)
            if not match or not _confirmed(label, match):
                continue
            if allowlisted and (severity != "critical" or _PLACEHOLDER.search(match.group(0))):
                findings.append(
                    Finding(
                        check=CHECK,
                        severity="info",
                        path=path,
                        line=number,
                        message=f"allowlisted {label} on line {number}",
                    )
                )
                continue
            findings.append(
                Finding(
                    check=CHECK,
                    severity=severity,  # type: ignore[arg-type]
                    path=path,
                    line=number,
                    message=f"possible {label} on line {number}",
                    fix_hint=f"remove it; a documented placeholder may carry '{ALLOW_MARKER}' on that line",
                )
            )
            break
    return findings


def check_sensitive(catalog: Catalog, config: KbConfig) -> list[Finding]:
    findings: list[Finding] = []
    for doc in catalog.documents:
        raw = doc.path.read_text(encoding="utf-8").replace("\r\n", "\n")
        findings.extend(scan_lines(raw.splitlines(), doc.rel_path))
    for path in sorted(catalog.docs_root.rglob("*.y*ml")):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(catalog.docs_root).as_posix()
            findings.extend(scan_lines(path.read_text(encoding="utf-8").splitlines(), rel))
    return findings


def redact(text: str | None) -> str | None:
    """Replace every sensitive match in ``text`` with a labelled placeholder."""
    if not text:
        return text
    out = text
    for label, pattern, _severity in _PATTERNS:
        out = pattern.sub(lambda m, label=label: f"[REDACTED:{label}]" if _confirmed(label, m) else m.group(0), out)
    return out


def scan_file(path: Path, rel: str) -> list[Finding]:
    return scan_lines(path.read_text(encoding="utf-8").splitlines(), rel)
