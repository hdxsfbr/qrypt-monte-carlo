"""Where a job's randomness comes from.

Terms
- *Entropy*: unpredictable bytes. Qrypt sells entropy produced by a quantum random number generator.
- *KiB*: kibibyte, 1,024 bytes. Each new job asks Qrypt for one KiB.
- *EntropySource*: anything with a ``fetch()`` method that returns one block. ``QryptEntropySource`` calls
  the real service; ``MockEntropySource`` returns fixed bytes or a chosen failure, for tests and local runs.

If Qrypt fails, ``fetch()`` raises ``EntropyError``. There is deliberately no fallback to the clock,
the operating system's random source or any other local source: a job without Qrypt entropy is
refused, not quietly downgraded.
"""

from __future__ import annotations

import base64
import binascii
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

QRYPT_URL = "https://api-eus.qrypt.com/api/v1/quantum-entropy"
BLOCK_BYTES = 1024
TIMEOUT_SECONDS = 3.0
USER_AGENT = "qrypt-monte-carlo/1.0"  # Qrypt's edge blocks the default Python-urllib agent


@dataclass(frozen=True)
class EntropyError(Exception):
    """A failed fetch. ``client_status`` is the HTTP status our API returns to its caller (502 or 503)."""

    cause: str
    client_status: int
    message: str

    def __str__(self) -> str:
        return f"{self.message} ({self.cause})"


# Qrypt status -> (cause, status we return, message). 401/403 are "bad gateway" (Qrypt refused us);
# the rest are "service unavailable" (try again later).
_STATUS_MAP = {
    401: ("qrypt_unauthorized", 502, "Qrypt rejected the request (missing or malformed auth)"),
    403: ("qrypt_forbidden", 502, "Qrypt token rejected or entropy quota reached"),
    429: ("qrypt_rate_limited", 503, "Qrypt rate limit"),
}
_UNAVAILABLE = ("qrypt_unavailable", 503, "Qrypt unavailable")
_BAD_RESPONSE = ("qrypt_bad_response", 503, "Qrypt returned a response we could not read")


def error_for_status(status: int) -> EntropyError:
    return EntropyError(*_STATUS_MAP.get(status, _UNAVAILABLE))


class EntropySource(Protocol):
    def fetch(self) -> bytes:
        """Return one block of ``BLOCK_BYTES`` bytes or raise ``EntropyError``."""
        ...


class QryptEntropySource:
    """One HTTPS GET per call, one attempt, 3-second timeout. The token is held in memory only."""

    def __init__(self, token: str, url: str = QRYPT_URL, timeout: float = TIMEOUT_SECONDS):
        if not token:
            raise ValueError("Qrypt token is empty")
        self._token = token
        self._url = url
        self._timeout = timeout

    def __repr__(self) -> str:  # never show the token
        return f"QryptEntropySource(url={self._url!r})"

    def fetch(self) -> bytes:
        request = urllib.request.Request(  # noqa: S310 - fixed https URL
            f"{self._url}?size=1",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise error_for_status(exc.code) from None
        except (TimeoutError, urllib.error.URLError, OSError):
            raise EntropyError(*_UNAVAILABLE) from None
        return parse_response(body)


def parse_response(body: bytes) -> bytes:
    """Qrypt answers ``{"random": ["<base64>"], ...}``; one KiB decodes to exactly 1,024 bytes."""
    try:
        data = json.loads(body)
        block = base64.b64decode(data["random"][0], validate=True)
    except (ValueError, KeyError, IndexError, TypeError, binascii.Error):
        raise EntropyError(*_BAD_RESPONSE) from None
    if len(block) != BLOCK_BYTES:
        raise EntropyError(*_BAD_RESPONSE)
    return block


class MockEntropySource:
    """Test double: returns ``block`` (default: a fixed pattern) or fails as told.

    ``fail_with`` is an HTTP status (401, 403, 429, 500, 503), ``"timeout"`` or ``"bad_json"``.
    ``calls`` counts fetches, so tests can prove that replay never calls Qrypt.
    """

    def __init__(self, block: bytes | None = None, fail_with: int | str | None = None):
        if block is None:
            block = bytes(range(256)) * (BLOCK_BYTES // 256)
        if len(block) != BLOCK_BYTES:
            raise ValueError(f"mock block must be {BLOCK_BYTES} bytes")
        self._block = block
        self._fail_with = fail_with
        self.calls = 0

    def fetch(self) -> bytes:
        self.calls += 1
        if self._fail_with is None:
            return self._block
        if self._fail_with == "timeout":
            raise EntropyError(*_UNAVAILABLE)
        if self._fail_with == "bad_json":
            raise EntropyError(*_BAD_RESPONSE)
        raise error_for_status(int(self._fail_with))
