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
| Build, milestone M1 (the two functions, secrets script, command-line client) | Next |
| Deployed endpoint | Not deployed yet. No AWS resources have been created. |

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
| [src/qmc/](src/qmc/) | The pricing engine: input checks, seed derivation, simulation, totals, Black-Scholes, Qrypt client |
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
block of bytes).

## Deployment settings

Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` (git ignores it) and set `alert_email`,
the address that gets budget and alarm emails. AWS sends a confirmation email after the first deploy; the
link in it must be clicked before alerts arrive.

**Concurrency** (how many copies of a function may run at once): the new account's Lambda limit is 10,
and AWS refuses per-function reservations at that size. Until the requested increase to 1,000 is granted,
the deployment uses `reserve_concurrency = false` and `worker_concurrency = 5`: the queue starts at most 5
workers at once, leaving room for the api function.

## Grader quick-start

Added once the build is done: configure AWS credentials, store the SSM parameters, `terraform apply`,
submit a job, replay it, `terraform destroy`.
