"""scripts/put-secrets.sh, run against a fake ``aws`` command (a small script placed first on PATH that
records how it was called). Real AWS is never contacted."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "put-secrets.sh"
QRYPT = "fake-qrypt-token-value"  # noqa: S105 - test value
API = "fake-api-key-" + "x" * 32

FAKE_AWS = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$LOG_DIR/argv"
case "$1 $2" in
  "sts get-caller-identity") echo "${FAKE_ACCOUNT}" ;;
  "ssm put-parameter")
    for a in "$@"; do case "$a" in file://*)
      cat "${a#file://}" >> "$LOG_DIR/inputs"; echo >> "$LOG_DIR/inputs"
      stat -c '%a' "${a#file://}" >> "$LOG_DIR/modes";; esac; done
    echo 1 ;;
esac
"""

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")


def run(tmp_path, env_text, *args, account="144249522427", profile=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "aws"
    fake.write_text(FAKE_AWS)
    fake.chmod(0o755)
    (tmp_path / ".env").write_text(env_text)
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir(exist_ok=True)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LOG_DIR": str(tmp_path),
        "FAKE_ACCOUNT": account,
        "HOME": str(tmp_path),
        "TMPDIR": str(tmpdir),
    }
    if profile:
        env["AWS_PROFILE"] = profile
    proc = subprocess.run(  # noqa: S603 - fixed script, test-controlled arguments
        [BASH, str(SCRIPT), *args], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
    )
    read = lambda name: (tmp_path / name).read_text() if (tmp_path / name).exists() else ""  # noqa: E731
    return proc, read("argv"), read("inputs"), read("modes")


def test_writes_both_parameters_without_secrets_on_the_command_line(tmp_path):
    proc, argv, inputs, modes = run(tmp_path, f'QRYPT_API_KEY="{QRYPT}"\nAPI_KEY={API}\nAWS_PROFILE=qmc\n')
    assert proc.returncode == 0, proc.stderr
    assert "wrote /qmc/dev/qrypt_api_key" in proc.stdout and "wrote /qmc/dev/api_key" in proc.stdout
    assert QRYPT not in argv and API not in argv  # never in the process list
    assert QRYPT not in proc.stdout + proc.stderr and API not in proc.stdout + proc.stderr
    assert "--profile qmc" in argv
    written = [json.loads(line) for line in inputs.splitlines() if line]
    assert [(w["Name"], w["Value"], w["Type"]) for w in written] == [
        ("/qmc/dev/qrypt_api_key", QRYPT, "SecureString"),
        ("/qmc/dev/api_key", API, "SecureString"),
    ]
    assert set(modes.split()) == {"600"}
    assert not list((tmp_path / "tmp").iterdir())  # the temporary file is removed


def test_refuses_another_account(tmp_path):
    proc, argv, inputs, _ = run(tmp_path, f"QRYPT_API_KEY={QRYPT}\nAPI_KEY={API}\n", account="788792938287")
    assert proc.returncode == 1 and "refusing" in proc.stderr
    assert "put-parameter" not in argv and inputs == ""


def test_refuses_another_profile(tmp_path):
    proc, argv, _, _ = run(tmp_path, f"QRYPT_API_KEY={QRYPT}\nAPI_KEY={API}\n", profile="default")
    assert proc.returncode == 1 and "only uses the 'qmc' profile" in proc.stderr
    assert argv == ""


def test_dry_run_writes_nothing(tmp_path):
    proc, argv, inputs, _ = run(tmp_path, f"QRYPT_API_KEY={QRYPT}\nAPI_KEY={API}\n", "--dry-run")
    assert proc.returncode == 0 and proc.stdout.count("dry run: would write") == 2
    assert "put-parameter" not in argv and inputs == ""


def test_placeholders_and_short_keys_are_skipped(tmp_path):
    env = "QRYPT_API_KEY=replace-with-your-qrypt-token\nAPI_KEY=short\n"
    proc, argv, _, _ = run(tmp_path, env)
    assert proc.returncode == 1 and "placeholder" in proc.stderr and "at least 32" in proc.stderr
    assert "put-parameter" not in argv


def test_env_file_is_not_executed(tmp_path):
    marker = tmp_path / "ran"
    proc, _, inputs, _ = run(tmp_path, f"touch {marker}\nQRYPT_API_KEY=$(touch {marker})\nAPI_KEY={API}\n")
    assert not marker.exists()
    assert f"$(touch {marker})" in inputs  # stored literally, not run
    assert proc.returncode == 0
