# AI usage disclosure

This project was built almost entirely by AI agents working under the direction of one person, Andre
Batista, who set the goals, made the account and spending decisions, and approved each step that touched
AWS or a shared system. This file says which tools did what, what shaped their output, and how the
results were checked.

## Terms

- **AI agent:** an AI model that can run commands and edit files on its own, not just answer questions.
- **Grok Bot:** the AI assistant Andre worked with in chat. It has two roles here:
  - the **coordinator**, which talked with Andre, broke the work into milestones, passed on his
    decisions and limits, and reviewed each milestone's report;
  - the **executor**, a separate agent session started by the coordinator for each milestone, which did the
    hands-on work.
- **Lab machine:** Andre's Linux workstation, where the repository lives and where the executor ran
  commands through a remote shell.
- **Moto:** a Python library that imitates AWS services in memory, so tests run without an AWS account.
- **CI (continuous integration):** the GitLab pipeline that re-runs the checks on every push.

## Who did what

| Work | Done by |
|------|---------|
| Reading the brief; research on AWS free-tier limits, Qrypt, Lambda behaviour and seeding methods (`docs/research.md`, with links to the sources) | Executor, using web search and the AWS and Qrypt documentation, plus read-only checks in AWS |
| Product requirements (`docs/PRD.md`), design (`docs/DESIGN.md`), requirements trace | Executor wrote them; Andre approved the design before any build work started |
| All Python code (simulation, seeding, Qrypt client, Lambda handlers, command-line client) and all tests | Executor |
| All Terraform (five modules) and the CI pipeline | Executor |
| Scripts (`put-secrets.sh`, benchmarks), diagram, README and other docs, including this file | Executor |
| Creating the dedicated AWS Free plan account and signing the CLI into it; getting the Qrypt token | Andre |
| Approvals: moving to the new account, `terraform apply` (deploy), enabling the CI runner for the project, requesting the Lambda concurrency increase from AWS, and running these submission tasks | Andre, each given in chat before the step was taken |
| Live checks, benchmarks and evidence files in `docs/evidence/` | Executor ran the commands; the files are the real output |
| Budget console screenshot and demo video | Andre (still to do at the time of writing) |

Git records every commit under Andre's name because the work was done in his repository with his git
settings; the commits themselves were written by the executor.

This file does not claim that a person reviewed every line of code. The checks people can rely on are the
automated tests and the live evidence described below.

## What shaped the AI's output

These materially shaped the solution, beyond the brief itself (`sources/cloud_quantum_seeded_monte_carlo.md`):

- **`AGENTS.md`**, the standing instructions in the repository for any coding agent: read the PRD,
  design and trace first; never print or commit secrets; keep the Qrypt token out of Terraform state;
  use only the dedicated AWS account through the `qmc` profile; stay inside always-free allowances; commit
  small and often.
- **Andre's limits, passed on by the coordinator for every milestone**, the most important being:
  - every AWS command uses the `qmc` profile, never the default one (which points at an older, paid
    account);
  - stop and report before anything that would cost money or depart from the always-free design;
  - keep Qrypt use tiny (well under the 10 MB cap and the request rate limit);
  - no hidden switches that bypass checks; the failure-injection switch for the demo is a visible
    Terraform setting that is off by default;
  - do not chase performance numbers: measure once and report;
  - do not invent test results;
  - write documentation in plain language and define every term.
- **Design decisions Andre approved** with the design (`docs/DESIGN.md`, approved before the build): one Lambda Function URL with a bearer
  key instead of API Gateway; DynamoDB with provisioned capacity inside the free amount; HKDF to turn one
  Qrypt block into per-shard seeds; failing the job (no fallback randomness) when Qrypt is unavailable.

## How the results were checked

**By automated tests, re-run on every push by CI:**

- 141 tests (`make test`), 95.8% line and branch coverage of the code. They cover the price staying
  within 3 standard errors of the Black-Scholes formula, seed derivation against the published HKDF test
  vectors, bit-identical replay including a fixed "golden" value, shard results being counted once even
  when a message is delivered twice, PARTIAL jobs, input validation, Qrypt errors and timeouts, the API
  key check, and the command-line client.
- The AWS parts of the handler tests use moto; the Qrypt client is replaced by a mock that returns fixed
  bytes, so the tests need no token and make no network calls.
- Static checks: `ruff` (Python style and common bugs), `terraform fmt` and `validate`, `tflint` and
  `checkov` (Terraform security rules).

**By hand, against the real deployment** (commands run by the executor; outputs saved unchanged in
`docs/evidence/`):

- 22 October, `m2-2026-10-22/`: deploy and no-drift plan, health check, rejected requests without a valid
  key, a 1,000,000-path job against the formula, bit-identical replay and a matching rerun on the lab
  machine, a forced shard failure ending PARTIAL, the message reaching the dead-letter queue, the alarm
  going off and clearing, metrics, budget, and a search of the logs and Terraform state for secrets.
- 22 October, `m3-2026-10-22/`: the submit-latency and 1M-path timing benchmarks.

**Problems the checks found** (kept here because they show the checks doing their job):

- Live use showed that Qrypt rejects a third request within about a second, stricter than its documented
  limit; the benchmark pacing was slowed and the finding recorded.
- The worker logs showed shards of the same job occasionally colliding when they update the job's shared
  counter. Retries recover every time so far, but it is recorded as an open weakness with a planned fix.
- The lint step (run before each push, and again in CI) caught formatting and style errors before they
  reached `main`.

## Where AI was not used

There is no AI feature in the product. Every price comes from the simulation code and is checked against
the closed-form formula; no AI model takes part in producing or checking results.
