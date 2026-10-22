"""The ``qmc`` command-line client, with the network replaced by a fake ``urlopen``."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from qmc import cli

JOB_ID = "11111111-1111-4111-8111-111111111111"


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QMC_URL", "https://example.lambda-url.us-east-1.on.aws/")
    monkeypatch.setenv("API_KEY", "k" * 40)
    sent: list = []
    replies: list = []

    def fake_urlopen(req, timeout):
        sent.append(req)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(json.dumps(reply).encode())

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    return sent, replies


def test_submit_wait_polls_until_complete(api, capsys):
    sent, replies = api
    replies += [
        {"job_id": JOB_ID, "status": "QUEUED"},
        {"status": "RUNNING", "progress": {"completed": 1, "shards": 2}},
        {"status": "COMPLETE", "result": {"estimate": 10.45}},
    ]
    assert cli.main(["submit", "--paths", "2000", "--shards", "2", "--wait"]) == 0
    assert sent[0].get_method() == "POST" and sent[0].full_url.endswith("/jobs")
    assert json.loads(sent[0].data)["paths"] == 2000
    assert sent[0].get_header("Authorization") == "Bearer " + "k" * 40
    out = capsys.readouterr()
    assert json.loads(out.out)["status"] == "COMPLETE" and "k" * 40 not in out.out + out.err


def test_get_list_replay_health_paths(api):
    sent, replies = api
    replies += [{}, {}, {"job_id": JOB_ID}, {}]
    assert cli.main(["get", JOB_ID]) == 0
    assert cli.main(["list", "--limit", "5", "--next", "abc"]) == 0
    assert cli.main(["replay", JOB_ID]) == 0
    assert cli.main(["health"]) == 0
    assert [r.full_url.split(".aws")[1] for r in sent] == [
        f"/jobs/{JOB_ID}",
        "/jobs?limit=5&next=abc",
        f"/jobs/{JOB_ID}/replay",
        "/health",
    ]


def test_http_error_is_reported_with_exit_1(api, capsys):
    _, replies = api
    body = io.BytesIO(json.dumps({"error": "job not found"}).encode())
    replies.append(urllib.error.HTTPError("u", 404, "Not Found", {}, body))
    assert cli.main(["get", JOB_ID]) == 1
    assert "HTTP 404: job not found" in capsys.readouterr().err


def test_unreachable_and_timeout(api, capsys):
    _, replies = api
    replies.append(urllib.error.URLError("no route"))
    assert cli.main(["health"]) == 1
    replies.append({"status": "RUNNING", "progress": {}})
    assert cli.main(["wait", JOB_ID, "--timeout", "0"]) == 1
    err = capsys.readouterr().err
    assert "could not reach" in err and "still RUNNING" in err


def test_missing_settings(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QMC_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    assert cli.main(["health"]) == 1
    (tmp_path / ".env").write_text(
        "# comment\nQMC_URL='https://x'\nAPI_KEY=replace-with-a-long-random-string\n"
    )
    assert cli.main(["health"]) == 1
    assert "set API_KEY" in capsys.readouterr().err


def test_local_matches_golden_value(capsys):
    args = ["local", "--seed-hex", "5a" * 32, "--paths", "10000", "--shards", "4"]
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["result"]["estimate_hex"] == "0x1.4712dd8387372p+3"
    assert cli.main(["local", "--seed-hex", "5a"]) == 1
