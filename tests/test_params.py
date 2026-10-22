import pytest

from qmc.params import JobParams, Limits, ValidationError, validate_job_request

GOOD = {"S0": 100, "K": 100, "r": 0.05, "sigma": 0.2, "T": 1, "paths": 1_000_000, "shards": 10}


def test_valid_request():
    req = validate_job_request(dict(GOOD))
    assert req.params == JobParams(100.0, 100.0, 0.05, 0.2, 1.0, 1_000_000, 10)
    assert req.fail_shards == ()
    assert req.params.to_dict()["paths"] == 1_000_000


def test_whole_number_given_as_float_is_accepted():
    assert validate_job_request(GOOD | {"paths": 1000.0, "shards": 2.0}).params.paths == 1000


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"sigma": 0}, "sigma"),
        ({"sigma": -0.2}, "sigma"),
        ({"sigma": 6}, "sigma"),
        ({"T": 0}, "T"),
        ({"T": -1}, "T"),
        ({"T": 101}, "T"),
        ({"S0": 0}, "S0"),
        ({"K": -5}, "K"),
        ({"r": 2}, "r"),
        ({"paths": 0}, "paths"),
        ({"paths": -10}, "paths"),
        ({"paths": 1}, "paths"),
        ({"paths": 10.5}, "paths"),
        ({"paths": 10_000_001}, "paths"),
        ({"shards": 0}, "shards"),
        ({"shards": 21}, "shards"),
        ({"paths": 5, "shards": 6}, "shards"),
        ({"paths": 5_000_000, "shards": 2}, "shards"),
        ({"S0": "100"}, "S0"),
        ({"K": None}, "K"),
        ({"r": True}, "r"),
        ({"paths": True}, "paths"),
        ({"paths": "many"}, "paths"),
        ({"sigma": float("nan")}, "sigma"),
        ({"T": float("inf")}, "T"),
        ({"extra": 1}, "extra"),
    ],
)
def test_invalid_inputs_name_the_field(change, field):
    with pytest.raises(ValidationError) as info:
        validate_job_request(GOOD | change)
    assert info.value.field == field
    assert field in str(info.value)


@pytest.mark.parametrize("name", list(GOOD))
def test_missing_field(name):
    body = dict(GOOD)
    del body[name]
    with pytest.raises(ValidationError) as info:
        validate_job_request(body)
    assert info.value.field == name


@pytest.mark.parametrize("body", [None, [], "text", 3])
def test_body_must_be_object(body):
    with pytest.raises(ValidationError):
        validate_job_request(body)


def test_fault_injection_rejected_unless_enabled():
    with pytest.raises(ValidationError) as info:
        validate_job_request(GOOD | {"fail_shards": [1]})
    assert "not enabled" in info.value.message


def test_fault_injection_when_enabled():
    limits = Limits(fault_injection=True)
    assert validate_job_request(GOOD | {"fail_shards": [3, 1, 3]}, limits).fail_shards == (1, 3)
    for bad in ([10], [-1], "1", [True]):
        with pytest.raises(ValidationError):
            validate_job_request(GOOD | {"fail_shards": bad}, limits)


def test_custom_limits():
    limits = Limits(max_paths=1000, max_shards=2, max_paths_per_shard=600)
    validate_job_request(GOOD | {"paths": 1000, "shards": 2}, limits)
    with pytest.raises(ValidationError):
        validate_job_request(GOOD | {"paths": 1001, "shards": 2}, limits)
