"""PBKDF2-SHA256 from the standard library, as the *arr apps use.

Encoded as ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` so the work factor can
be raised later without invalidating stored passwords.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_SCHEME = "pbkdf2_sha256"
# OWASP's 2023 recommendation for PBKDF2-HMAC-SHA256.
DEFAULT_ITERATIONS = 600_000


class Pbkdf2PasswordHasher:
    def __init__(self, iterations: int = DEFAULT_ITERATIONS) -> None:
        self._iterations = iterations

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = _derive(password, salt, self._iterations)
        return f"{_SCHEME}${self._iterations}${_b64(salt)}${_b64(digest)}"

    def verify(self, password: str, encoded: str) -> bool:
        parsed = _parse(encoded)
        if parsed is None:
            return False
        iterations, salt, expected = parsed
        return hmac.compare_digest(_derive(password, salt, iterations), expected)

    def needs_rehash(self, encoded: str) -> bool:
        parsed = _parse(encoded)
        return parsed is None or parsed[0] != self._iterations


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _parse(encoded: str) -> tuple[int, bytes, bytes] | None:
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != _SCHEME:
        return None
    try:
        return int(parts[1]), base64.b64decode(parts[2]), base64.b64decode(parts[3])
    except ValueError:
        return None
