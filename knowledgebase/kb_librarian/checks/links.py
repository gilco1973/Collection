"""Link integrity: internal targets must exist; external hosts are policy-checked."""

import ipaddress
import socket
from urllib.parse import unquote, urlsplit

import httpx

from kb_librarian.catalog.catalog import Catalog, Document, Link
from kb_librarian.checks.base import Finding
from kb_librarian.kbconfig import KbConfig

CHECK = "links"


def _internal_target_exists(catalog: Catalog, doc: Document, link: Link) -> bool:
    target = link.target.split("#", 1)[0]
    if not target:
        return True
    resolved = (doc.path.parent / unquote(target)).resolve()
    if resolved.is_dir():
        resolved = resolved / "README.md"
    return resolved.exists() and catalog.docs_root.resolve() in resolved.parents


def _probe_allowed(host: str) -> bool:
    """Never probe private, loopback, link-local or non-public targets from the runner (SSRF).

    The host is resolved and every address must be globally routable; shorthand
    literals (``127.1``, octal) resolve to loopback and are rejected the same way.
    """
    if not host or "." not in host or host.endswith((".internal", ".local", ".example", ".localhost")):
        return False
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(_public(ipaddress.ip_address(a)) for a in addresses)


_NEVER = [ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "224.0.0.0/4", "ff00::/8")]


def _public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Globally routable and not a NAT64/6to4 wrapper or multicast, which ``is_global`` lets through."""
    return address.is_global and not address.is_multicast and not any(address in net for net in _NEVER)


def _external_status(client: httpx.Client, url: str) -> int | None:
    try:
        # Redirects are never followed: a public URL must not steer the probe to a private target.
        response = client.head(url, follow_redirects=False)
        if response.status_code == 405:
            with client.stream("GET", url, follow_redirects=False) as streamed:
                return streamed.status_code  # the body is never read: a status is all the check needs
        return response.status_code
    except httpx.HTTPError:
        return None


def check_links(
    catalog: Catalog,
    config: KbConfig,
    offline: bool = True,
    client: httpx.Client | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    trusted = set(config.links.trusted_hosts)
    owns_client = client is None and not offline
    client = client or (httpx.Client(timeout=10.0) if not offline else None)
    try:
        for doc in catalog.documents:
            for link in doc.links:
                if link.target.startswith("mailto:"):
                    continue
                if not link.is_external:
                    if not _internal_target_exists(catalog, doc, link):
                        findings.append(
                            Finding(
                                check=CHECK,
                                severity="error",
                                path=doc.rel_path,
                                line=link.line,
                                message=f"broken internal link '{link.target}'",
                                fix_hint="fix the path or remove the link",
                            )
                        )
                    continue
                host = urlsplit(link.target).hostname or ""
                if offline:
                    if host not in trusted:
                        findings.append(
                            Finding(
                                check=CHECK,
                                severity="info",
                                path=doc.rel_path,
                                line=link.line,
                                message=f"external host '{host}' is not in links.trusted_hosts (unverified offline)",
                            )
                        )
                    continue
                if not _probe_allowed(host) or urlsplit(link.target).scheme != "https":
                    findings.append(
                        Finding(
                            check=CHECK,
                            severity="info",
                            path=doc.rel_path,
                            line=link.line,
                            message=f"external link '{link.target}' not probed (non-public host or not https)",
                        )
                    )
                    continue
                status = _external_status(client, link.target)  # type: ignore[arg-type]
                if status is None or status >= 400:
                    findings.append(
                        Finding(
                            check=CHECK,
                            severity="warning",
                            path=doc.rel_path,
                            line=link.line,
                            message=f"external link '{link.target}' returned {status or 'no response'}",
                        )
                    )
    finally:
        if owns_client and client is not None:
            client.close()
    return findings
