"""API and worker handlers against moto's in-memory DynamoDB, SQS and SSM. No real AWS, no Qrypt."""

from __future__ import annotations

import json
import time

import pytest

from conftest import BLOCK, call, drain, receive

JOB = {"S0": 100, "K": 100, "r": 0.05, "sigma": 0.2, "T": 1, "paths": 20000, "shards": 4}


def submit(body=None):
    status, data, _ = call("POST", "/jobs", body or JOB)
    assert status == 202, data
    return data["job_id"]


def metric_lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.startswith('{"_aws"')]


def metrics_named(text: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for line in metric_lines(text):
        for d in line["_aws"]["CloudWatchMetrics"][0]["Metrics"]:
            out.setdefault(d["Name"], []).append(line[d["Name"]])
    return out


# ---- auth and routing -------------------------------------------------------------------------------


def test_missing_or_wrong_key_is_401(aws):
    assert call("GET", "/jobs", key=None)[:2] == (401, {"error": "unauthorized"})
    assert call("GET", "/jobs", key="wrong")[0] == 401


def test_iam_mode_skips_bearer_check(aws, monkeypatch):
    monkeypatch.setenv("AUTH_TYPE", "AWS_IAM")
    assert call("GET", "/jobs", key=None)[0] == 200


def test_unknown_routes_and_methods(aws):
    assert call("GET", "/nope")[0] == 404
    assert call("DELETE", "/jobs")[0] == 405
    assert call("POST", "/health")[2]["allow"] == "GET"
    status, data, _ = call("GET", "/jobs/not-a-uuid")
    assert (status, data["error"]) == (404, "job not found")
    status, data, _ = call("GET", "/jobs/00000000-0000-4000-8000-000000000000")
    assert status == 404 and data["job_id"] == "00000000-0000-4000-8000-000000000000"


def test_health_ok_and_degraded(aws, monkeypatch):
    status, data, _ = call("GET", "/health")
    assert status == 200 and data["checks"] == {"dynamodb": "ok", "ssm": "ok"}
    aws.ssm.delete_parameter(Name="/qmc/test/qrypt_api_key")
    status, data, _ = call("GET", "/health")
    assert status == 503 and data["checks"]["ssm"].startswith("unreachable")


def test_unexpected_error_is_plain_500(aws, monkeypatch):
    from handlers import store

    def boom(*_):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(store, "list_jobs", boom)
    status, data, _ = call("GET", "/jobs")
    assert status == 500 and data == {"error": "internal error", "request_id": "req-1"}


# ---- submit -----------------------------------------------------------------------------------------


def test_bad_input_is_400_naming_the_field(aws):
    status, data, _ = call("POST", "/jobs", {**JOB, "sigma": -1})
    assert status == 400 and data["field"] == "sigma"
    assert call("POST", "/jobs", raw="{not json")[1]["field"] == "body"
    assert call("POST", "/jobs", raw="x" * 5000)[1]["error"].startswith("body: must be at most")
    status, data, _ = call("POST", "/jobs", {**JOB, "fail_shards": [1]})
    assert status == 400 and data["field"] == "fail_shards"  # fault injection is off


def test_submit_queues_one_message_per_shard(aws, capsys):
    job_id = submit()
    records = receive(aws.sqs, aws.queue)
    assert sorted(json.loads(r["body"])["shard_index"] for r in records) == [0, 1, 2, 3]
    assert {json.loads(r["body"])["paths"] for r in records} == {5000}
    status, data, _ = call("GET", f"/jobs/{job_id}")
    assert status == 200 and data["status"] == "QUEUED"
    assert data["master_seed_hex"] == BLOCK[:32].hex()
    assert data["seed_source"]["provider"] == "qrypt" and "block" not in data["seed_source"]
    assert aws.entropy.calls == 1
    m = metrics_named(capsys.readouterr().out)
    assert m["JobsSubmitted"] == [1] and m["EntropyKiB"] == [1]


def test_more_than_ten_shards_uses_several_batches(aws):
    submit({**JOB, "paths": 20000, "shards": 20})
    seen = set()
    while records := receive(aws.sqs, aws.queue):
        for r in records:
            seen.add(json.loads(r["body"])["shard_index"])
            aws.sqs.delete_message(QueueUrl=aws.queue, ReceiptHandle=r["receiptHandle"])
    assert seen == set(range(20))


@pytest.mark.parametrize(
    ("fail_with", "status", "cause"),
    [(403, 502, "qrypt_forbidden"), (429, 503, "qrypt_rate_limited"), ("timeout", 503, "qrypt_unavailable")],
)
def test_qrypt_errors_write_no_job(aws, monkeypatch, capsys, fail_with, status, cause):
    from handlers import api
    from qmc.entropy import MockEntropySource

    monkeypatch.setattr(api, "entropy_factory", lambda: MockEntropySource(fail_with=fail_with))
    got, data, _ = call("POST", "/jobs", JOB)
    assert (got, data["cause"]) == (status, cause)
    assert call("GET", "/jobs")[1]["jobs"] == []
    assert receive(aws.sqs, aws.queue) == []
    assert metrics_named(capsys.readouterr().out)["QryptErrors"] == [1]


def test_rate_limit_returns_429_with_retry_after(aws, monkeypatch):
    from handlers import store

    monkeypatch.setattr(store, "RATE_LIMIT", 2)
    submit()
    submit()
    status, data, headers = call("POST", "/jobs", JOB)
    assert status == 429 and int(headers["retry-after"]) >= 1 and data["retry_after_s"] >= 1


def test_queue_failure_is_503_with_job_id(aws, monkeypatch):
    from handlers import common

    real = common.client("sqs")

    class Failing:
        def send_message_batch(self, **kw):
            return {"Failed": [{"Id": e["Id"]} for e in kw["Entries"]], "Successful": []}

        def __getattr__(self, name):
            return getattr(real, name)

    monkeypatch.setattr("handlers.api.client", lambda s: Failing() if s == "sqs" else common.client(s))
    status, data, _ = call("POST", "/jobs", JOB)
    assert status == 503 and "job_id" in data


# ---- worker -----------------------------------------------------------------------------------------


def test_end_to_end_complete_matches_local_pipeline(aws, capsys):
    from qmc.params import JobParams
    from qmc.pipeline import run_job

    job_id = submit()
    assert drain(aws.sqs, aws.queue) == 4
    status, data, _ = call("GET", f"/jobs/{job_id}")
    assert status == 200 and data["status"] == "COMPLETE"
    assert data["progress"] == {"completed": 4, "failed": 0, "shards": 4}
    local = run_job(JobParams(100.0, 100.0, 0.05, 0.2, 1.0, 20000, 4), BLOCK[:32])
    assert data["result"]["estimate_hex"] == local.estimate.estimate_hex  # bit for bit
    assert data["result"]["estimate"] == local.estimate.estimate
    assert abs(data["black_scholes"] - 10.450583572185565) < 1e-12
    assert data["result"]["std_errors_from_black_scholes"] < 5
    m = metrics_named(capsys.readouterr().out)
    assert sum(m["PathsSimulated"]) == 20000 and len(m["ShardDurationMs"]) == 4
    assert "ShardFailures" not in m


def test_running_is_shown_while_shards_arrive(aws):
    from handlers import worker

    job_id = submit()
    worker.handler({"Records": receive(aws.sqs, aws.queue, 1)}, None)
    data = call("GET", f"/jobs/{job_id}")[1]
    assert data["status"] == "RUNNING" and data["progress"]["completed"] == 1


def test_duplicate_delivery_counts_once(aws, capsys):
    from handlers import worker

    job_id = submit()
    records = receive(aws.sqs, aws.queue)
    worker.handler({"Records": [records[0], records[0]]}, None)  # same shard delivered twice
    data = call("GET", f"/jobs/{job_id}")[1]
    assert data["progress"]["completed"] == 1
    assert len(metrics_named(capsys.readouterr().out)["PathsSimulated"]) == 1
    worker.handler({"Records": records[1:]}, None)
    worker.handler({"Records": [records[2]]}, None)  # after the job is finished: ignored
    data = call("GET", f"/jobs/{job_id}")[1]
    assert data["status"] == "COMPLETE" and data["progress"]["completed"] == 4


def test_fault_injection_ends_partial_after_last_attempt(aws, monkeypatch, capsys):
    from handlers import worker

    monkeypatch.setenv("ENABLE_FAULT_INJECTION", "true")
    job_id = submit({**JOB, "fail_shards": [2]})
    records = receive(aws.sqs, aws.queue)
    bad = next(r for r in records if json.loads(r["body"])["shard_index"] == 2)
    worker.handler({"Records": [r for r in records if r is not bad]}, None)
    for attempt in (1, 2):
        bad["attributes"]["ApproximateReceiveCount"] = str(attempt)
        with pytest.raises(worker.InjectedFailure):
            worker.handler({"Records": [bad]}, None)
        assert call("GET", f"/jobs/{job_id}")[1]["status"] == "RUNNING"  # still retrying
    bad["attributes"]["ApproximateReceiveCount"] = "3"
    with pytest.raises(worker.InjectedFailure):
        worker.handler({"Records": [bad]}, None)
    data = call("GET", f"/jobs/{job_id}")[1]
    assert data["status"] == "PARTIAL" and data["failed_shards"] == [2] and "result" not in data
    assert data["progress"] == {"completed": 3, "failed": 1, "shards": 4}
    assert metrics_named(capsys.readouterr().out)["ShardFailures"] == [1]


def test_worker_ignores_unknown_job(aws):
    from handlers import worker

    body = json.dumps({"job_id": "00000000-0000-4000-8000-000000000000", "shard_index": 0, "shard_count": 1})
    assert worker.handler({"Records": [{"body": body, "receiptHandle": "x"}]}, None) == {"processed": 1}


def test_stale_job_is_marked_partial_on_read(aws, monkeypatch):
    from handlers import api, worker

    job_id = submit()
    records = receive(aws.sqs, aws.queue)
    worker.handler({"Records": records[:3]}, None)
    monkeypatch.setattr(api, "STALE_AFTER_S", -1)
    data = call("GET", f"/jobs/{job_id}")[1]
    missing = json.loads(records[3]["body"])["shard_index"]
    assert data["status"] == "PARTIAL" and data["failed_shards"] == [missing]
    worker.handler({"Records": records[3:]}, None)  # a late shard cannot turn it COMPLETE
    assert call("GET", f"/jobs/{job_id}")[1]["status"] == "PARTIAL"


# ---- replay and listing ------------------------------------------------------------------------------


def test_replay_is_bit_identical_and_skips_qrypt(aws, capsys):
    job_id = submit()
    status, data, _ = call("POST", f"/jobs/{job_id}/replay")
    assert (status, data["error"]) == (409, "only a COMPLETE job can be replayed")
    drain(aws.sqs, aws.queue)
    calls_before = aws.entropy.calls
    status, data, _ = call("POST", f"/jobs/{job_id}/replay")
    assert status == 202 and data["replay_of"] == job_id
    drain(aws.sqs, aws.queue)
    replay = call("GET", f"/jobs/{data['job_id']}")[1]
    assert replay["status"] == "COMPLETE" and aws.entropy.calls == calls_before
    assert replay["replay_check"]["bit_identical"] is True
    assert replay["seed_source"] == {"replay_of": job_id}
    assert metrics_named(capsys.readouterr().out)["EntropyKiB"] == [1, 0]
    assert call("POST", "/jobs/00000000-0000-4000-8000-000000000000/replay")[0] == 404


def test_list_is_newest_first_with_pages(aws):
    ids = []
    for _ in range(3):
        ids.append(submit())
        time.sleep(0.002)  # distinct millisecond timestamps
    assert call("GET", "/jobs")[1]["next"] is None
    status, page1, _ = call("GET", "/jobs", query={"limit": "2"})
    assert status == 200 and [j["job_id"] for j in page1["jobs"]] == ids[:0:-1]
    page2 = call("GET", "/jobs", query={"limit": "2", "next": page1["next"]})[1]
    assert [j["job_id"] for j in page2["jobs"]] == ids[:1]
    assert call("GET", "/jobs", query={"limit": "0"})[0] == 400
    assert call("GET", "/jobs", query={"limit": "x"})[0] == 400
    assert call("GET", "/jobs", query={"next": "garbage"})[1]["field"] == "next"


def test_metric_lines_are_valid_emf(aws, capsys):
    submit()
    lines = metric_lines(capsys.readouterr().out)
    meta = lines[0]["_aws"]["CloudWatchMetrics"][0]
    assert meta["Namespace"] == "QMC" and meta["Dimensions"] == [["Environment"]]
    assert lines[0]["Environment"] == "test"
