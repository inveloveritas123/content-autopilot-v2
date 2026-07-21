"""SSRF-Schutz: verhindert, dass benutzergesteuerte URLs auf interne/private
Netzwerkziele zeigen (W1, 2026-07-21).

Angriff: Ein Tenant legt eine Source mit URL `http://169.254.169.254/...`
(Cloud-Metadata) oder `http://10.0.0.5/...` (internes Netz) an — der Server
fetcht sie serverseitig und leakt interne Ressourcen/Credentials.

Schutz (Defense-in-Depth):
1. Schema muss http/https sein.
2. Host wird per DNS aufgelöst; JEDE aufgelöste IP muss global-routbar sein
   (nicht private/loopback/link-local/reserved/multicast). Damit greift der
   Schutz auch bei DNS-Rebinding-freundlichen Hostnamen, die auf 127.0.0.1 o.ä.
   zeigen.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """URL zeigt (potenziell) auf ein internes/nicht-öffentliches Ziel."""


def _ip_is_public(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_public_url(url: str) -> None:
    """Wirft UnsafeURLError, wenn die URL nicht sicher öffentlich fetchbar ist.

    Löst den Host per DNS auf und verlangt, dass ALLE Adressen global-routbar sind.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Nur http/https erlaubt, nicht {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL ohne Host")

    # Host kann direkt eine IP sein → sofort prüfen.
    try:
        ipaddress.ip_address(host)
        if not _ip_is_public(host):
            raise UnsafeURLError(f"URL zeigt auf nicht-öffentliche IP: {host}")
        return
    except ValueError:
        pass  # kein IP-Literal → DNS-Auflösung

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Host nicht auflösbar: {host}") from exc

    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise UnsafeURLError(f"Host {host} lieferte keine Adressen")
    for ip in resolved:
        if not _ip_is_public(ip):
            raise UnsafeURLError(
                f"Host {host} löst auf nicht-öffentliche IP {ip} auf (SSRF-Schutz)"
            )


def is_public_url(url: str) -> bool:
    """Bool-Variante von assert_public_url (True = sicher fetchbar)."""
    try:
        assert_public_url(url)
        return True
    except UnsafeURLError:
        return False
