# Submission checklist

Each item the brief asks for (`sources/cloud_quantum_seeded_monte_carlo.md`, "Submission requirements"),
where it is in this repository, and its state on 22 October 2026. The full list of requirements, with
evidence for each, is in [REQUIREMENTS_TRACE.md](REQUIREMENTS_TRACE.md).

| Brief item | Where | State |
|------------|-------|-------|
| Repository with a README | [README.md](../README.md) | Done, but hosted on GitLab (labs.gauntletai.com); the brief says GitHub |
| AI_USAGE.md | [AI_USAGE.md](../AI_USAGE.md) | Done |
| `.env.example` and a mock Qrypt client, so the tests run without a token | [.env.example](../.env.example); `MockEntropySource` in [src/qmc/entropy.py](../src/qmc/entropy.py) | Done |
| Architecture diagram with every AWS resource and data flow | [architecture.svg](architecture.svg) (also [PNG](architecture.png)), source [architecture.mmd](architecture.mmd) | Done |
| Grader quick-start: credentials, secret in SSM, apply, submit, replay, destroy | README, "Grader quick-start" | Done. Checked from a fresh clone: 141 tests pass offline, `terraform validate` passes, and a job plus a bit-identical replay ran against the deployed endpoint |
| Cost note with the free-tier arithmetic | [COST.md](COST.md) | Done |
| Budget configuration screenshot | `docs/images/budget-console.png`, linked from COST.md | **Missing**: to be taken from the AWS Budgets console |
| Deployed endpoint URL, kept up through grading | README, Status table | Done; stays up through Monday 26 October 2026 (Central Time), then destroyed. Graders need the API key, which is not in the repository |
| One-line description, 120 characters or fewer | Top of README | Done (118 characters) |
| Demo video, 5 minutes or less: apply, a job completing, the Black-Scholes comparison, replay, the dead-letter-queue alarm | Not in the repository | **Missing** |
| Benchmark results (latency, 1M-path run time, cost, rebuild time) | [evidence/m3-2026-10-22/README.md](evidence/m3-2026-10-22/README.md), [COST.md](COST.md) | Done |
| Terraform for all infrastructure | [infra/](../infra/) | Done (25 resources; the two SSM secrets are created by `scripts/put-secrets.sh` so they stay out of Terraform state) |

Optional ("stretch") items: the CloudWatch dashboard and the Checkov scan in CI are done; Step Functions,
the queued entropy retry, Value-at-Risk, per-branch environments and per-job cost figures are not.
