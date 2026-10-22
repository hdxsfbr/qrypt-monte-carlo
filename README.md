# Quantum-Seeded Monte Carlo Platform on AWS

A serverless platform on AWS that prices a stock option by simulation, seeds every job from Qrypt quantum
randomness, and can replay any past job to the exact same answer. Everything is built with Terraform.

**Plain-language summary.** A *Monte Carlo* job estimates a number by simulating many random futures and
averaging them. Here the number is the fair price of a *European call option* (the right to buy a stock at a
set price on a set date). The *Black-Scholes* formula gives the exact answer for this option, so we can prove
the simulation is right. Each job gets its starting randomness (its *seed*) from Qrypt's quantum random
number service, splits into parallel pieces (*shards*), and stores everything needed to replay it later.

## Status

| Stage | State |
|-------|-------|
| Brief captured (`sources/`) | Done |
| Research (`docs/research.md`) | Done |
| Requirements (`docs/PRD.md`, `docs/REQUIREMENTS_TRACE.md`) | Done |
| Design (`docs/DESIGN.md`) | Approved |
| Build, milestone M0 (engine, mock Qrypt client, CI, Terraform modules) | Done: 107 tests pass; Terraform checks clean |
| Build, milestone M1 (the two functions, secrets script, command-line client) | Done: 141 tests pass, including the functions against simulated AWS services |
| Deploy and measure (milestone M2) | Deployed 22 October 2026. Live checks passed: health, a 1,000,000-path job within 3 standard errors of Black-Scholes, bit-identical replay, a forced shard failure ending PARTIAL with the dead-letter-queue alarm firing and recovering, metrics and budget (`docs/evidence/m2-2026-10-22/`). Timing measurements (benchmarks) not done yet |
| Deployed endpoint | `https://4z55v6fqv2s45myovdzkge4h2q0qxjpz.lambda-url.us-east-1.on.aws` (every request needs the API key; see Command-line client) |
| CI | GitLab pipeline runs on every push (ruff, pytest, terraform validate, TFLint, Checkov); all passed for commit 739579a |

## AWS account, cost and grading window

- **Account:** a dedicated AWS account on the **Free plan** (`144249522427`, CLI profile `qmc`, region
  `us-east-1`). On the Free plan, usage beyond the always-free allowances is paid from $100 of credits
  (valid until 22 April 2027) rather than billed; when credits run out AWS pauses the account instead of
  charging. A $1/month budget alarm on the whole account still warns early.
- **Grading window:** the deployed endpoint stays up through **Monday 26 October 2026 (Central Time)**,
  then `terraform destroy` removes everything.
- **Expected cost through then: $0.** At most about 5 days deployed; everything stays inside the monthly
  always-free allowances (worked figures in `docs/DESIGN.md`, section 11), so the credits stay unused.

## Docs index

| Document | What it covers |
|----------|----------------|
| [sources/cloud_quantum_seeded_monte_carlo.md](sources/cloud_quantum_seeded_monte_carlo.md) | The full project brief, as provided |
| [sources/portal-page.md](sources/portal-page.md) | The project's portal page (summary and metadata) |
| [docs/research.md](docs/research.md) | AWS free allowances, Qrypt API, Lambda, seeding and reliability research, with sources and small live checks |
| [docs/PRD.md](docs/PRD.md) | Product requirements: problem, users, goals, every requirement, benchmarks, edge cases, deliverables |
| [docs/REQUIREMENTS_TRACE.md](docs/REQUIREMENTS_TRACE.md) | Every requirement with its source line, status and evidence |
| [docs/DESIGN.md](docs/DESIGN.md) | Architecture, diagram, data model, seed flow, error handling, measurement, security, tests, cost |
| [AGENTS.md](AGENTS.md) | How coding agents should work in this repository |
| [src/qmc/](src/qmc/) | The pricing engine: input checks, seed derivation, simulation, totals, Black-Scholes, Qrypt client, and the `qmc` command-line client |
| [src/handlers/](src/handlers/) | The two Lambda functions: `api` (the web API) and `worker` (simulates one shard per queue message) |
| [scripts/](scripts/) | `put-secrets.sh` (stores the two secrets in AWS) and `qmc` (command-line client) |
| [tests/](tests/) | Unit tests, all runnable without AWS or a Qrypt token |
| [infra/](infra/) | Terraform: one root module plus modules `data`, `workers`, `api`, `observability`, `budget` |
| [.gitlab-ci.yml](.gitlab-ci.yml) | The CI pipeline (checks run by GitLab on every push) |
| [.env.example](.env.example) | The local settings file template (copy to `.env`; never commit `.env`) |

Coming with the build: `AI_USAGE.md`, a grader quick-start in this README, and the cost note with the Budget screenshot.

## Running the checks locally

Needs Python 3.13. The engine uses only Python's standard library; the test tools are in
`requirements-dev.txt`.

```sh
make venv        # create .venv and install the test tools
make test        # unit tests with a coverage report (fails below 80%)
make lint        # ruff: style and common-bug checks
make check       # everything CI runs: the above plus terraform fmt and validate, tflint, checkov
                 # (needs terraform, tflint and checkov installed)
```

*Coverage* is the share of code lines the tests run. *TFLint* checks Terraform for mistakes `terraform
validate` misses. *Checkov* scans Terraform for insecure settings; every rule it is told to skip has a
comment saying why. No test calls AWS or Qrypt: Qrypt is replaced by a mock (a stand-in that returns a fixed
block of bytes), and the function tests use *moto*, a library that imitates DynamoDB, SQS and Parameter Store
in memory.

## Deployment settings

Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` (git ignores it) and set `alert_email`,
the address that gets budget and alarm emails. AWS sends a confirmation email after the first deploy; the
link in it must be clicked before alerts arrive.

**Concurrency** (how many copies of a function may run at once): the new account's Lambda limit is 10,
and AWS refuses per-function reservations at that size. An increase to 1,000 was requested on 22 October 2026 (AWS support case 179270556400278, still open). Until it is granted,
the deployment uses `reserve_concurrency = false` and `worker_concurrency = 5`: the queue starts at most 5
workers at once, leaving room for the api function.

## Storing the secrets

The API needs two secrets: the Qrypt token and the *API key* (the password callers send in the
`Authorization: Bearer ...` header). Both live in AWS SSM Parameter Store as encrypted *SecureString*
parameters, created outside Terraform so the values never enter Terraform's state file.

```sh
cp .env.example .env          # then fill in QRYPT_API_KEY and API_KEY (at least 32 characters)
scripts/put-secrets.sh --dry-run   # checks the account and lists what it would write
scripts/put-secrets.sh             # writes /qmc/dev/qrypt_api_key and /qmc/dev/api_key
```

The script only runs with the `qmc` profile and only if that profile belongs to account `144249522427`. It
reads `.env` without executing it and never prints the values or puts them on a command line.

## Command-line client

`scripts/qmc` talks to the deployed API. It reads `QMC_URL` (the Function URL, from `terraform output`) and
`API_KEY` from the environment or from `.env`.

```sh
scripts/qmc health                                   # can the API reach its table and secrets?
scripts/qmc submit --paths 1000000 --shards 10 --wait   # start a job and wait for the answer
scripts/qmc get <job id>                             # status, progress and result
scripts/qmc list --limit 5                           # recent jobs, newest first
scripts/qmc replay <job id> --wait                   # same seed again; shows bit_identical
scripts/qmc local --seed-hex <64 hex chars> --paths 10000 --shards 4   # run the engine here, no network
```

Job states: **QUEUED** (accepted, waiting for workers), **RUNNING** (some shards done), **COMPLETE** (all
shards done; result available), **PARTIAL** (one or more shards failed after three tries, or never arrived
within 10 minutes; no result is given, and `failed_shards` lists them).

## Grader quick-start

You need: AWS credentials for an account of your own (the commands below assume a CLI profile), Terraform
1.9 or newer, Python 3.13, and a Qrypt token.

```sh
cp .env.example .env            # fill in QRYPT_API_KEY, and API_KEY (any random string of 32+ characters)
cp infra/terraform.tfvars.example infra/terraform.tfvars   # set alert_email
scripts/put-secrets.sh          # stores both secrets in SSM Parameter Store (see Storing the secrets)
terraform -chdir=infra init
terraform -chdir=infra apply    # about 1.5 minutes; prints function_url
echo "QMC_URL=$(terraform -chdir=infra output -raw function_url)" >> .env
scripts/qmc health
scripts/qmc submit --paths 1000000 --shards 10 --wait   # compare estimate with black_scholes
scripts/qmc replay <job id> --wait                     # bit_identical: true
terraform -chdir=infra destroy  # removes everything; then delete the two SSM parameters
```

`put-secrets.sh` is pinned to this project's account (`144249522427`, profile `qmc`); in another account
change `EXPECTED_ACCOUNT` and the `qmc` profile check in the script, and `allowed_account_ids` in `infra/variables.tf`.

To repeat the forced-failure check, apply with `-var enable_fault_injection=true`, then
`scripts/qmc submit --paths 100000 --shards 4 --fail-shards 2 --wait`; the job ends PARTIAL and the message
reaches the dead-letter queue, which sets off the `qmc-dev-dlq-depth` alarm within about 5 minutes. Apply
again without the variable to switch it off.
