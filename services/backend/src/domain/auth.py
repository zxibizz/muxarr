"""Rules for who may reach the API, independent of how a request is read."""

from __future__ import annotations

import ipaddress

from src.domain.enums import AuthMethod, AuthRequired

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
MAX_USERNAME_LENGTH = 64

# Spelled out: ``ip_address.is_private`` also covers the documentation ranges,
# which are routable in practice and must not skip the login.
_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def credentials_problem(username: str, password: str) -> str | None:
    """Why this username/password pair is unusable, or None if it is fine."""
    if not username.strip():
        return "the username must not be empty"
    if len(username.strip()) > MAX_USERNAME_LENGTH:
        return f"the username must be at most {MAX_USERNAME_LENGTH} characters"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"the password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"the password must be at most {MAX_PASSWORD_LENGTH} characters"
    return None


def is_local_address(host: str | None) -> bool:
    """Loopback, RFC 1918, ULA or link-local: an address that never crosses the internet."""
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in network for network in _LOCAL_NETWORKS)


def login_required(method: AuthMethod, required: AuthRequired, client_host: str | None) -> bool:
    """Whether a request without an API key must carry a session."""
    if method == "external":
        return False
    return not (required == "disabled_for_local_addresses" and is_local_address(client_host))
