"""Qrypt client tests. ``urlopen`` is replaced, so nothing here touches the network."""

import base64
import email.message
import io
import json
import pathlib
import re
import urllib.error

import pytest

from qmc import entropy
from qmc.entropy import EntropyError, MockEntropySource, QryptEntropySource, parse_response

BLOCK = bytes((i * 7) % 256 for i in range(1024))
TOKEN = "test-token-not-real"  # noqa: S105


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ok_body(block=BLOCK):
    return json.dumps({"random": [base64.b64encode(block).decode()], "size": 1}).encode()


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def install(result):
        def fake_urlopen(request, timeout):
            seen["request"] = request
            seen["timeout"] = timeout
            if isinstance(result, BaseException):
                raise result
            return _Response(result)

        monkeypatch.setattr(entropy.urllib.request, "urlopen", fake_urlopen)
        return seen

    return install


def _http_error(code):
    return urllib.error.HTTPError(entropy.QRYPT_URL, code, "x", email.message.Message(), None)


def test_successful_fetch_sends_the_right_request(captured):
    seen = captured(_ok_body())
    assert QryptEntropySource(TOKEN).fetch() == BLOCK
    req = seen["request"]
    assert req.full_url == "https://api-eus.qrypt.com/api/v1/quantum-entropy?size=1"
    assert req.get_header("Authorization") == f"Bearer {TOKEN}"
    assert req.get_header("Accept") == "application/json"
    assert req.get_header("User-agent") == entropy.USER_AGENT
    assert seen["timeout"] == 3.0


@pytest.mark.parametrize(
    ("code", "cause", "status"),
    [
        (401, "qrypt_unauthorized", 502),
        (403, "qrypt_forbidden", 502),
        (429, "qrypt_rate_limited", 503),
        (500, "qrypt_unavailable", 503),
        (503, "qrypt_unavailable", 503),
    ],
)
def test_http_errors_are_mapped(captured, code, cause, status):
    captured(_http_error(code))
    with pytest.raises(EntropyError) as info:
        QryptEntropySource(TOKEN).fetch()
    assert (info.value.cause, info.value.client_status) == (cause, status)


def test_403_message_names_token_or_quota(captured):
    captured(_http_error(403))
    with pytest.raises(EntropyError, match="token rejected or entropy quota reached"):
        QryptEntropySource(TOKEN).fetch()


@pytest.mark.parametrize("exc", [TimeoutError(), ConnectionResetError(), urllib.error.URLError("dns")])
def test_network_failures_are_unavailable(captured, exc):
    captured(exc)
    with pytest.raises(EntropyError) as info:
        QryptEntropySource(TOKEN).fetch()
    assert info.value.client_status == 503


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        b'{"random": []}',
        b'{"random": ["***"]}',
        json.dumps({"random": [base64.b64encode(b"short").decode()]}).encode(),
    ],
)
def test_bad_responses(body):
    with pytest.raises(EntropyError) as info:
        parse_response(body)
    assert info.value.cause == "qrypt_bad_response"


def test_token_is_never_shown():
    source = QryptEntropySource(TOKEN)
    assert TOKEN not in repr(source)
    assert TOKEN not in str(entropy.error_for_status(401))
    with pytest.raises(ValueError):
        QryptEntropySource("")


def test_mock_source():
    mock = MockEntropySource()
    assert len(mock.fetch()) == 1024
    assert MockEntropySource(BLOCK).fetch() == BLOCK
    assert mock.calls == 1
    with pytest.raises(ValueError):
        MockEntropySource(b"short")


@pytest.mark.parametrize(
    ("fail_with", "status"),
    [(401, 502), (403, 502), (429, 503), (500, 503), ("timeout", 503), ("bad_json", 503)],
)
def test_mock_failures(fail_with, status):
    with pytest.raises(EntropyError) as info:
        MockEntropySource(fail_with=fail_with).fetch()
    assert info.value.client_status == status


def test_no_local_randomness_fallback_anywhere_in_the_engine():
    # EC-1: seeds come from Qrypt or from a stored seed, never from the clock or the operating system.
    banned = re.compile(r"os\.urandom|import secrets|from secrets|random\.seed\(|time\.time\(|SystemRandom")
    src = pathlib.Path(entropy.__file__).parent
    offenders = [p.name for p in src.rglob("*.py") if banned.search(p.read_text())]
    assert offenders == []
