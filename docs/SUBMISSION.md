# Submission checklist

Each item the brief asks for (`sources/cloud_quantum_seeded_monte_carlo.md`, "Submission requirements"),
where it is in this repository, and its state on 24 October 2026. The full list of requirements, with
evidence for each, is in [REQUIREMENTS_TRACE.md](REQUIREMENTS_TRACE.md).

| Brief item | Where | State |
|------------|-------|-------|
| Repository with a README | [README.md](../README.md) | Done. Hosted on GitLab (https://labs.gauntletai.com/andrebatista/qrypt-monte-carlo) by team decision; the brief says GitHub, and there is no GitHub copy |
| AI_USAGE.md | [AI_USAGE.md](../AI_USAGE.md) | Done |
| `.env.example` and a mock Qrypt client, so the tests run without a token | [.env.example](../.env.example); `MockEntropySource` in [src/qmc/entropy.py](../src/qmc/entropy.py) | Done |
| Architecture diagram with every AWS resource and data flow | [architecture.svg](architecture.svg) (also [PNG](architecture.png)), source [architecture.mmd](architecture.mmd) | Done |
| Grader quick-start: credentials, secret in SSM, apply, submit, replay, destroy | README, "Grader quick-start" | Done. Checked from a fresh clone on 22 October 2026: 141 tests pass offline, `terraform validate` passes, and a job plus a bit-identical replay ran against the deployed endpoint |
| Cost note with the free-tier arithmetic | [COST.md](COST.md) | Done |
| Budget configuration screenshot | `docs/images/budget-console.png`, linked from COST.md | Done: $1.00 limit, $0.00 used, Healthy |
| Deployed endpoint URL, kept up through grading | README, Status table | Done; stays up through Monday 26 October 2026 (Central Time), then destroyed. Every request needs an API key, which is not published; graders do not need it (the video and `docs/evidence/` show the live runs, and the quick-start deploys a private copy). Without a key the endpoint answers `401 unauthorized` |
| One-line description, 120 characters or fewer | Top of README | Done (118 characters) |
| Demo video, 5 minutes or less: apply, a job completing, the Black-Scholes comparison, replay, the dead-letter-queue alarm | Uploaded; link given in the submission form (**video URL: to be added by Andre**) | Done: 4 min 20 s, recorded 22 October 2026 against a short-lived second copy of the stack (`qmc-demo`), destroyed afterwards |
| Benchmark results (latency, 1M-path run time, cost, rebuild time) | [evidence/m3-2026-10-22/README.md](evidence/m3-2026-10-22/README.md), [COST.md](COST.md) | Done |
| Terraform for all infrastructure | [infra/](../infra/) | Done (25 resources; the two SSM secrets are created by `scripts/put-secrets.sh` so they stay out of Terraform state) |

Optional ("stretch") items: the CloudWatch dashboard and the Checkov scan in CI are done; Step Functions,
the queued entropy retry, Value-at-Risk, per-branch environments and per-job cost figures are not.
