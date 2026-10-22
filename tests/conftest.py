"""Shared test fixtures. ``aws`` starts moto (a library that fakes DynamoDB, SQS and SSM in memory), so the
handler tests never reach real AWS."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

TABLE = "qmc-test-jobs"
API_KEY = "test-api-key-0123456789"
QRYPT_TOKEN = "test-qrypt-token"  # noqa: S105 - a fake value for the fake SSM
BLOCK = bytes(range(256)) * 4  # a fixed 1 KiB block


@pytest.fixture
def aws(monkeypatch):
    moto = pytest.importorskip("moto")
    import boto3

    from handlers import api, common

    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "QMC_ENV": "test",
        "TABLE_NAME": TABLE,
        "QRYPT_PARAM_NAME": "/qmc/test/qrypt_api_key",
        "API_KEY_PARAM_NAME": "/qmc/test/api_key",
        "AUTH_TYPE": "BEARER",
        "MAX_RECEIVE_COUNT": "3",
        "ENABLE_FAULT_INJECTION": "false",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    with moto.mock_aws():
        common.reset_clients()
        api._secrets.clear()
        ddb = boto3.client("dynamodb")
        ddb.create_table(
            TableName=TABLE,
            AttributeDefinitions=[
                {"AttributeName": n, "AttributeType": "S"} for n in ("pk", "sk", "gsi1pk", "gsi1sk")
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 10, "WriteCapacityUnits": 10},
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "by_created",
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                }
            ],
        )
        sqs = boto3.client("sqs")
        dlq = sqs.create_queue(QueueName="qmc-test-dlq")["QueueUrl"]
        attrs = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])
        dlq_arn = attrs["Attributes"]["QueueArn"]
        queue = sqs.create_queue(
            QueueName="qmc-test-shards",
            Attributes={
                "VisibilityTimeout": "0",
                "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}),
            },
        )["QueueUrl"]
        monkeypatch.setenv("QUEUE_URL", queue)
        ssm = boto3.client("ssm")
        ssm.put_parameter(Name="/qmc/test/qrypt_api_key", Value=QRYPT_TOKEN, Type="SecureString")
        ssm.put_parameter(Name="/qmc/test/api_key", Value=API_KEY, Type="SecureString")

        from qmc.entropy import MockEntropySource

        source = MockEntropySource(BLOCK)
        monkeypatch.setattr(api, "entropy_factory", lambda: source)
        yield SimpleNamespace(ddb=ddb, sqs=sqs, ssm=ssm, queue=queue, dlq=dlq, entropy=source)
        common.reset_clients()


def call(method: str, path: str, body=None, key: str | None = API_KEY, query: dict | None = None, raw=None):
    """Invoke the api handler with a Function URL style event; returns (status, parsed body, headers)."""
    from handlers import api

    headers = {"content-type": "application/json"}
    if key is not None:
        headers["authorization"] = f"Bearer {key}"
    event = {
        "rawPath": path,
        "headers": headers,
        "requestContext": {"http": {"method": method}},
        "body": raw if raw is not None else (json.dumps(body) if body is not None else None),
        "isBase64Encoded": False,
    }
    if query:
        event["queryStringParameters"] = query
    resp = api.handler(event, SimpleNamespace(aws_request_id="req-1"))
    return resp["statusCode"], json.loads(resp["body"]), resp["headers"]


def receive(sqs, queue: str, max_messages: int = 10) -> list[dict]:
    """Pull messages and shape them like the records SQS hands to a Lambda trigger."""
    resp = sqs.receive_message(
        QueueUrl=queue,
        MaxNumberOfMessages=max_messages,
        MessageSystemAttributeNames=["ApproximateReceiveCount"],
    )
    return [
        {
            "body": m["Body"],
            "receiptHandle": m["ReceiptHandle"],
            "attributes": {"ApproximateReceiveCount": m["Attributes"]["ApproximateReceiveCount"]},
        }
        for m in resp.get("Messages", [])
    ]


def drain(sqs, queue: str) -> int:
    """Run the worker on every queued message until the queue is empty; returns messages processed."""
    from handlers import worker

    count = 0
    while records := receive(sqs, queue):
        for r in records:
            worker.handler({"Records": [r]}, None)
            sqs.delete_message(QueueUrl=queue, ReceiptHandle=r["receiptHandle"])
            count += 1
    return count
