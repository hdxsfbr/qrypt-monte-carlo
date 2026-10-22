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
| Build | In progress (milestone M0: skeleton and core engine) |
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

Coming with the build: `AI_USAGE.md`, `.env.example`, a grader quick-start in this README, and the cost note.

## Grader quick-start

Added once the build is done: configure AWS credentials, store the SSM parameters, `terraform apply`,
submit a job, replay it, `terraform destroy`.
