# Product Requirements: Quantum-Seeded Monte Carlo Platform on AWS

Source documents: `sources/cloud_quantum_seeded_monte_carlo.md` (the brief, cited below as **B:line**) and
`sources/portal-page.md`. Every requirement is listed with its source in `docs/REQUIREMENTS_TRACE.md`.

## Glossary
- **Monte Carlo simulation:** estimate a number by simulating many random outcomes and averaging them.
- **European call option:** the right (not the duty) to buy a stock at a fixed *strike* price `K` on one
  fixed date. Its payoff on that date is `max(price − K, 0)`.
- **Black-Scholes:** the textbook formula that gives the exact fair price of a European call. Inputs: today's
  price `S0`, strike `K`, interest rate `r`, volatility `sigma` (how much the price jumps around), time to
  expiry `T` in years.
- **Path:** one simulated future for the stock price. **Shard:** a slice of the job's paths run by one worker.
- **Standard error (SE):** how far the simulated average is likely to be from the true value; it shrinks
  as the number of paths grows. **95% confidence interval:** estimate ± 1.96 × SE.
- **Seed:** the starting number for a random number generator; the same seed gives the same "random" numbers.
  **Master seed:** a job's 256-bit seed from Qrypt. **Derived seed:** a shard's seed calculated from the master.
- **Qrypt entropy:** random bytes from Qrypt's quantum random number service.
- **Replay:** re-running a job from its stored seed and parameters to reproduce the answer exactly.
- **Bit-identical:** the same number down to the last binary digit, not just "close".
- **Idempotent:** doing something twice has the same effect as doing it once.
- **DLQ (dead-letter queue):** a side queue that collects messages that failed too many times.
- **p50 / p95:** the time within which 50% / 95% of requests finish.
- **Terraform:** a tool that creates cloud resources from code files. **Drift:** differences between the
  code and what actually exists.
- **IAM (Identity and Access Management):** AWS permissions. **Least privilege:** each part gets only the
  permissions it needs.
- AWS service names (Lambda, Function URL, SQS, DynamoDB, SNS, CloudWatch, SSM Parameter Store, Budgets)
  are defined in `docs/research.md`.

## 1. Problem
Quant teams price options and estimate risk with Monte Carlo simulations. Two things often go wrong: seeds
are weak or reused, so "independent" runs are secretly correlated; and the infrastructure is hand-built in a
web console, so nobody can reproduce a run or explain its bill (B:17-20). Auditors need to reproduce any
reported number (B:39-40).

**In two sentences:** we will build a serverless AWS platform, entirely defined in Terraform, that prices a
European call by Monte Carlo, seeds every job from Qrypt quantum randomness, and can replay any job to a
bit-identical result. It must cost $0 at rest and at the reference load, and prove correctness against the
Black-Scholes formula.

## 2. Users (B:33-35)
| User | Needs |
|------|-------|
| Quant analyst | Submit a pricing job; read progress and the result with its confidence interval |
| Platform operator | Deploy and tear down with one command; see metrics and alarms; keep cost at $0 |
| Auditor | Replay a past job and confirm the result matches exactly; see where the seed came from |

## 3. Goals and non-goals
**Goals**
- All six core requirements working end to end on a real deployment (B:137-168).
- Fail-closed seeding: never fall back to a local or time-based seed (B:188-190).
- Reliable under duplicate delivery and worker failure (B:191-195).
- $0 steady-state cost with the arithmetic shown, and a budget alarm as a backstop (B:28, B:216).
- Clean, modular Terraform with clean destroy and no drift (B:126-127, B:204-205, B:251-252).

**Non-goals**
- Other option types or pricing models beyond the stretch Value-at-Risk workload (B:177).
- A web user interface; the platform is an HTTPS API used with `curl` or a small script.
- Real-time streaming results; callers poll `GET /jobs/{id}`.
- Multi-region or high availability beyond what Lambda, SQS and DynamoDB give by default.
- Chasing benchmark numbers beyond the stated targets; each is measured once with the stated method and
  reported honestly.

## 4. Functional requirements

### Core (must-have)
| ID | Requirement | Acceptance check | Source |
|----|-------------|------------------|--------|
| FR-1 | `POST /jobs` accepts `{S0, K, r, sigma, T, paths, shards}`, validates it, fetches one Qrypt entropy block, derives a 256-bit master seed, writes the job record, enqueues one SQS message per shard | Returns a job id within the latency budget; the record holds the master seed (hex), the parameters and status `QUEUED` | B:139-144 |
| FR-2 | Each shard's seed is derived deterministically from the master seed and shard index, never from time or a shared global generator | A committed test shows shard seeds are distinct and the same master seed always gives the same shard seeds | B:145-150 |
| FR-3 | Workers read SQS, simulate their paths and write `{sum, sum_sq, n}` per shard; when all shards finish, the job is combined into an estimate, standard error and 95% confidence interval | `GET /jobs/{id}` shows progress, then `COMPLETE` with the estimate and interval | B:151-156 |
| FR-4 | With S0=100, K=100, r=0.05, sigma=0.2, T=1 and 1,000,000 paths, the estimate is within 3 standard errors of Black-Scholes | A committed test and a deployed run both show it | B:157-160 |
| FR-5 | `POST /jobs/{id}/replay` re-runs a job from its stored master seed and parameters | The replayed estimate is bit-identical to the original | B:161-163 |
| FR-6 | Terraform creates an AWS Budget (about $1/month) with an email/SNS alert; CloudWatch custom metrics: jobs submitted, paths simulated, entropy KiB consumed, shard failures; at least two alarms: worker errors and DLQ depth > 0 | A forced worker failure trips the DLQ alarm and sends a notification | B:164-168 |
| FR-7 | `GET /jobs` lists jobs; returns an empty list on a fresh deployment | Empty list on first run | B:206-207 |
| FR-8 | `GET /jobs/{id}` for an unknown id returns 404 with a clear message | 404 with message | B:207-208 |
| FR-9 | `GET /health` checks that DynamoDB and SSM are reachable | Reports each check | B:256 |

### Stretch (bonus; see DESIGN for which we plan)
| ID | Stretch goal | Source |
|----|--------------|--------|
| ST-1 | Step Functions orchestration with retry and wait-for-completion | B:172 |
| ST-2 | CloudWatch dashboard for job and entropy metrics | B:173 |
| ST-3 | `PENDING_ENTROPY`: hold jobs and retry entropy with backoff instead of rejecting | B:174-175 |
| ST-4 | Infrastructure security scan (Checkov or tfsec) in CI with justified suppressions | B:176 |
| ST-5 | Portfolio Value-at-Risk workload | B:177 |
| ST-6 | Ephemeral per-branch environments created and destroyed by CI | B:178-179 |
| ST-7 | Per-job cost attribution (estimated GB-seconds and request count in the result) | B:180-181 |

## 5. Edge cases and failure modes (B:183-208)
| ID | Situation | Expected behaviour |
|----|-----------|--------------------|
| EC-1 | Qrypt returns 401/403/429/500/503 or times out at submit | Job rejected with a clear error naming the cause; never seeded locally or from the clock |
| EC-2 | SQS delivers a shard message twice | Shard write is idempotent on `job_id + shard_index`; paths are never double-counted |
| EC-3 | A shard keeps failing | After the set retries it lands in the DLQ; the job is `PARTIAL` with failed shard indexes, never `COMPLETE` with a wrong total |
| EC-4 | Lambda timeout risk | Shard size is capped so a worker finishes well under its timeout; oversized `paths/shards` is rejected at submit |
| EC-5 | Burst of submissions | Never more than 30 Qrypt requests per 10 seconds (rate-limit the submit path) |
| EC-6 | Cost runaway | Reserved concurrency on workers and a maximum `paths` per job; larger requests rejected |
| EC-7 | Invalid inputs: zero or negative `sigma`, `T`, `paths`; `shards` > `paths`; non-numeric fields | 400 with a clear message |
| EC-8 | Teardown | `terraform destroy` removes every resource; a second `terraform plan` after apply shows no changes |
| EC-9 | Empty or first run | `GET /jobs` returns an empty list; unknown id returns 404 |

## 6. Non-functional requirements

### Performance benchmarks (B:210-217)
| ID | Target | Value | Measurement method |
|----|--------|-------|--------------------|
| NFR-1 | Submit API latency | < 800 ms p95, warm | 50 submissions from a script; report p50 and p95 |
| NFR-2 | Job wall-clock time | 1,000,000 paths in < 60 s | Time from submit to `COMPLETE`, 5 runs |
| NFR-3 | Steady-state cost | $0 at 100 jobs/day of 1M paths | Arithmetic against always-free allowances (requests, GB-seconds, DynamoDB, SQS) |
| NFR-4 | Environment rebuild | `terraform apply` from empty < 10 min | Timed from a clean account or region |

### Security, privacy and compliance (B:232-245)
| ID | Requirement |
|----|-------------|
| SEC-1 | `QRYPT_API_KEY` is an SSM SecureString created out-of-band (CLI or console), never a Terraform variable, so it never lands in Terraform state; the reason is documented |
| SEC-2 | One IAM role per function; each touches only its own table, queue or parameter; no `*` actions or resources |
| SEC-3 | No anonymous job submission: Function URL uses `AWS_IAM`, or a bearer key checked against SSM |
| SEC-4 | DynamoDB and SQS encrypted at rest (AWS-owned or AWS-managed keys); TLS in transit |
| SEC-5 | Structured logs carrying the job id; no tokens in logs; log retention set explicitly (14 days) |
| SEC-6 | All inputs validated server-side |

### Code quality and engineering (B:247-257, B:121-133)
| ID | Requirement |
|----|-------------|
| CQ-1 | Test coverage ≥ 80% on simulation math, seed derivation, aggregation and input validation |
| CQ-2 | Terraform: one root module plus modules `api`, `workers`, `data`, `observability`, `budget`; variables and outputs documented; `terraform fmt` and `validate` clean |
| CQ-3 | Thin handlers; simulation and aggregation are pure functions testable without AWS |
| CQ-4 | Graceful degradation per the edge cases; no unhandled exceptions in handlers |
| CQ-5 | CI runs unit tests, linter, `terraform validate` and `tflint` on every push |
| CQ-6 | Dependencies fit inside Lambda package limits; function language Python |
| CQ-7 | Correctness verified by committed tests (closed form, seed determinism and uniqueness, bit-identical replay, idempotent aggregation), not by an AI model (B:219-228) |
| CQ-8 | Only always-free services; no NAT gateway, load balancer, EC2, RDS, Secrets Manager or API Gateway; provisioned DynamoDB (or on-demand only if shown to be $0); SQS long polling (B:116-119) |
| CQ-9 | Total live Qrypt usage ≤ 10 MB (10,240 KiB) for the whole assessment; one 1 KiB call per job (B:94-97) |

### Prerequisites (B:10-13)
| ID | Requirement |
|----|-------------|
| PRE-1 | Before the timebox: an AWS account with billing alerts, a working Qrypt token, Terraform and the AWS CLI installed and signed in. Status: all in place (see `docs/research.md`, section 8) |

## 7. Deliverables (B:259-280)
| ID | Deliverable |
|----|-------------|
| D-1 | Repository with README (GitLab, private; the brief says GitHub) |
| D-2 | `AI_USAGE.md`: AI tools used, for what, and prompts or settings that shaped the solution |
| D-3 | `.env.example` for local runs, and a mock Qrypt client so tests run without a token |
| D-4 | Architecture diagram (Mermaid) showing every AWS resource and data flow |
| D-5 | Grader quick-start in the README: AWS credentials, store the SSM parameter, `terraform apply`, submit a job, replay it, `terraform destroy` |
| D-6 | Cost note: free-tier arithmetic and a screenshot of the Budget configuration |
| D-7 | Deployed endpoint URL, kept up through grading, then destroyed |
| D-8 | One-line project description (≤ 120 characters) |
| D-9 | Demo video (≤ 5 minutes) showing `terraform apply`, a job running to completion, the Black-Scholes comparison, a bit-identical replay, and the DLQ alarm firing |
| D-10 | Benchmark report with the measured numbers (from NFR-1 to NFR-4) |

**Submission documents:** README (with quick-start and one-line description), `AI_USAGE.md`,
`docs/PRD.md`, `docs/DESIGN.md` (with diagram), `docs/REQUIREMENTS_TRACE.md`, cost note with Budget
screenshot, benchmark report, deployed URL, demo video.

Proposed one-line description (109 characters): "Terraform-built serverless AWS Monte Carlo option pricer,
seeded by Qrypt quantum entropy, with exact replay."

## 8. Evaluation rubric (B:282-292)
Core functions 30, infrastructure as code 20, reliability 15, security 10, cost and observability 10,
correctness tests 5, docs/AI disclosure/demo 10. Pass at 70 of 100.

## 9. Timeline (2-day timebox, starts when the design is approved)
| Milestone | Content | Target |
|-----------|---------|--------|
| M0 Skeleton | Repo layout, pure Python core with tests (seeds, simulation, aggregation, validation, mock Qrypt), CI green | Day 1 morning |
| M1 Infrastructure | Terraform modules, deploy, health endpoint, submit and worker path working | Day 1 afternoon |
| M2 Reliability | Idempotency, DLQ, `PARTIAL`, rate limit, replay, alarms, budget, forced-failure demo | Day 2 morning |
| M3 Measure and document | Benchmarks, cost note, Budget screenshot, quick-start, `AI_USAGE.md`, chosen stretch goals | Day 2 afternoon |
| M4 Demo | Video script and recording, final submission | End of day 2 |

## 10. Open questions
1. **Budget alert email:** which address should receive budget and alarm emails? (It has to be confirmed by
   clicking a link AWS sends.)
2. **Region:** `us-east-1` (already the default, closest to Qrypt's US East endpoint). OK?
3. **API authentication:** bearer key checked against SSM (graders can call our URL with plain `curl`), with
   `AWS_IAM` as a Terraform switch for graders who deploy in their own account. OK?
4. **Budget scope:** filter the $1 budget to this project's services, since Route 53 already costs about
   $1/month in this account. OK?
5. **Due date:** when is the submission due, and how long must the endpoint stay up for grading?
6. **GitHub:** the brief asks for a GitHub repository; do you want a GitHub mirror, or is GitLab enough?
7. **Stretch goals:** OK with the ones proposed in the design (dashboard, Checkov in CI, per-job cost,
   `PENDING_ENTROPY` if time allows)?
