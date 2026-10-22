"""``qmc``: a small command-line client for the deployed API (standard library only).

    scripts/qmc health
    scripts/qmc submit --paths 1000000 --shards 10 --wait
    scripts/qmc get JOB_ID
    scripts/qmc list --limit 5
    scripts/qmc replay JOB_ID --wait
    scripts/qmc wait JOB_ID
    scripts/qmc local --seed-hex 5a5a... --paths 10000 --shards 4   (no network: runs the engine here)

Settings come from the environment, or from a ``.env`` file in the current folder:
``QMC_URL`` (the Function URL printed by Terraform) and ``API_KEY`` (the bearer key). The key is sent only
in the Authorization header and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FINISHED = {"COMPLETE", "PARTIAL"}
TIMEOUT_S = 30


class CliError(Exception):
    pass


def read_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    """KEY=VALUE lines; the file is read, never executed."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def settings() -> tuple[str, str]:
    file = read_dotenv()
    url = os.environ.get("QMC_URL") or file.get("QMC_URL", "")
    key = os.environ.get("API_KEY") or file.get("API_KEY", "")
    if not url:
        raise CliError("set QMC_URL (the Function URL from `terraform output api_url`)")
    if not key or key.startswith("replace-with"):
        raise CliError("set API_KEY (the same value stored in SSM by scripts/put-secrets.sh)")
    return url.rstrip("/"), key


def request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url, key = settings()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # noqa: S310 - the URL is the user's own API address
        url + path,
        data=data,
        method=method,
        headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        try:
            detail = json.loads(err.read() or b"{}")
        except json.JSONDecodeError:
            detail = {"error": err.reason}
        raise CliError(f"HTTP {err.code}: {detail.get('error', detail)}") from err
    except urllib.error.URLError as err:
        raise CliError(f"could not reach {url}: {err.reason}") from err


def wait_for(job_id: str, timeout_s: float, interval_s: float = 1.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        _, job = request("GET", f"/jobs/{job_id}")
        if job["status"] in FINISHED:
            return job
        if time.monotonic() >= deadline:
            raise CliError(f"job {job_id} still {job['status']} after {timeout_s:.0f} s")
        p = job.get("progress", {})
        print(f"{job['status']}: {p.get('completed', 0)}/{p.get('shards', '?')} shards", file=sys.stderr)
        time.sleep(interval_s)


def job_body(args: argparse.Namespace) -> dict:
    body = {k: getattr(args, k) for k in ("S0", "K", "r", "sigma", "T", "paths", "shards")}
    if args.fail_shards:
        body["fail_shards"] = args.fail_shards
    return body


def show(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def run_local(args: argparse.Namespace) -> dict:
    from qmc.params import validate_job_request
    from qmc.pipeline import run_job

    seed = bytes.fromhex(args.seed_hex)
    if len(seed) != 32:
        raise CliError("--seed-hex must be 64 hex characters (32 bytes)")
    params = validate_job_request(job_body(args)).params
    out = run_job(params, seed)
    return {"params": params.to_dict(), "result": out.estimate.to_dict(), "black_scholes": out.black_scholes}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qmc", description="Client for the Qrypt-seeded Monte Carlo API.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="check the deployment can reach its table and secrets")

    def add_job_args(sp):
        sp.add_argument("--S0", type=float, default=100.0, help="spot price today")
        sp.add_argument("--K", type=float, default=100.0, help="strike price")
        sp.add_argument("--r", type=float, default=0.05, help="risk-free rate per year")
        sp.add_argument("--sigma", type=float, default=0.2, help="volatility per year")
        sp.add_argument("--T", type=float, default=1.0, help="years to expiry")
        sp.add_argument("--paths", type=int, default=1_000_000, help="simulated price paths")
        sp.add_argument("--shards", type=int, default=10, help="pieces the work is split into")
        sp.add_argument("--fail-shards", type=int, nargs="*", default=[], help=argparse.SUPPRESS)

    submit = sub.add_parser("submit", help="start a job")
    add_job_args(submit)
    get = sub.add_parser("get", help="show one job")
    get.add_argument("job_id")
    lst = sub.add_parser("list", help="recent jobs, newest first")
    lst.add_argument("--limit", type=int, default=20)
    lst.add_argument("--next", help="page token from a previous list")
    replay = sub.add_parser("replay", help="rerun a COMPLETE job with the same seed")
    replay.add_argument("job_id")
    wait = sub.add_parser("wait", help="wait until a job is COMPLETE or PARTIAL")
    wait.add_argument("job_id")
    local = sub.add_parser("local", help="run the engine on this computer with a given seed (no network)")
    local.add_argument("--seed-hex", required=True)
    add_job_args(local)
    for sp in (submit, replay, wait):
        sp.add_argument("--timeout", type=float, default=300.0, help="seconds to wait (default 300)")
    for sp in (submit, replay):
        sp.add_argument("--wait", action="store_true", help="wait for the result")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "health":
            show(request("GET", "/health")[1])
        elif args.command == "local":
            show(run_local(args))
        elif args.command == "get":
            show(request("GET", f"/jobs/{args.job_id}")[1])
        elif args.command == "list":
            query = f"?limit={args.limit}" + (f"&next={args.next}" if args.next else "")
            show(request("GET", f"/jobs{query}")[1])
        elif args.command == "wait":
            show(wait_for(args.job_id, args.timeout))
        else:
            path = "/jobs" if args.command == "submit" else f"/jobs/{args.job_id}/replay"
            _, data = request("POST", path, job_body(args) if args.command == "submit" else None)
            show(wait_for(data["job_id"], args.timeout) if args.wait else data)
    except CliError as err:
        print(f"qmc: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
