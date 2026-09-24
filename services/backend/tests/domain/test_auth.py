from __future__ import annotations

import ipaddress

import pytest

from src.domain.auth import (
    client_address,
    credentials_problem,
    is_local_address,
    login_required,
)
from src.infrastructure.auth.hasher import Pbkdf2PasswordHasher

PROXY = (ipaddress.ip_network("172.18.0.2/32"),)
TAILNET = (ipaddress.ip_network("100.64.0.0/10"),)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.0.10",
        "169.254.1.1",
        "::1",
        "fd00::1",
        "::ffff:192.168.1.1",
    ],
)
def test_local_addresses(host: str) -> None:
    assert is_local_address(host)


@pytest.mark.parametrize("host", ["8.8.8.8", "203.0.113.9", "2001:4860::8888", "", None, "muxarr"])
def test_non_local_addresses(host: str | None) -> None:
    assert not is_local_address(host)


def test_external_never_asks_for_a_login() -> None:
    assert not login_required("external", "enabled", "8.8.8.8")


def test_forms_waives_the_login_only_for_local_callers_when_told_to() -> None:
    assert login_required("forms", "enabled", "127.0.0.1")
    assert not login_required("forms", "disabled_for_local_addresses", "127.0.0.1")
    assert login_required("forms", "disabled_for_local_addresses", "8.8.8.8")


def test_custom_local_networks_replace_the_defaults() -> None:
    relaxed = "disabled_for_local_addresses"

    assert not login_required("forms", relaxed, "100.101.102.103", TAILNET)
    assert login_required("forms", relaxed, "192.168.1.20", TAILNET)


class TestClientAddress:
    def test_an_untrusted_peer_is_the_client_whatever_it_claims(self) -> None:
        assert client_address("203.0.113.9", "127.0.0.1", PROXY) == "203.0.113.9"

    def test_nothing_is_believed_without_trusted_proxies(self) -> None:
        assert client_address("172.18.0.2", "203.0.113.9", ()) == "172.18.0.2"

    def test_a_trusted_proxy_names_the_client(self) -> None:
        assert client_address("172.18.0.2", "203.0.113.9, 172.18.0.2", PROXY) == "203.0.113.9"

    def test_a_prefix_written_by_the_client_is_ignored(self) -> None:
        """The proxy appends what it saw; everything left of that is the client's."""
        forwarded = "127.0.0.1, 203.0.113.9, 172.18.0.2"

        assert client_address("172.18.0.2", forwarded, PROXY) == "203.0.113.9"

    def test_a_chain_of_trusted_proxies_is_followed(self) -> None:
        both = (*PROXY, ipaddress.ip_network("10.0.0.0/8"))

        assert client_address("172.18.0.2", "198.51.100.7, 10.1.1.1", both) == "198.51.100.7"

    def test_a_trusted_proxy_without_a_header_is_the_client(self) -> None:
        assert client_address("172.18.0.2", None, PROXY) == "172.18.0.2"

    def test_garbage_is_returned_and_so_never_local(self) -> None:
        client = client_address("172.18.0.2", "not-an-ip", PROXY)

        assert client == "not-an-ip"
        assert not is_local_address(client)


def test_credentials_problem() -> None:
    assert credentials_problem("admin", "long-enough") is None
    assert credentials_problem("  ", "long-enough") is not None
    assert credentials_problem("admin", "short") is not None


class TestHasher:
    hasher = Pbkdf2PasswordHasher(iterations=1_000)

    def test_round_trip(self) -> None:
        encoded = self.hasher.hash("hunter2hunter2")

        assert encoded.startswith("pbkdf2_sha256$1000$")
        assert self.hasher.verify("hunter2hunter2", encoded)
        assert not self.hasher.verify("hunter3hunter3", encoded)

    def test_salted(self) -> None:
        assert self.hasher.hash("same") != self.hasher.hash("same")

    def test_garbage_never_verifies(self) -> None:
        assert not self.hasher.verify("x", "not-a-hash")
        assert not self.hasher.verify("x", "pbkdf2_sha256$abc$%%%$%%%")

    def test_a_changed_work_factor_asks_for_a_rehash(self) -> None:
        encoded = self.hasher.hash("pw")

        assert not self.hasher.needs_rehash(encoded)
        assert Pbkdf2PasswordHasher(iterations=2_000).needs_rehash(encoded)
