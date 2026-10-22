# Requirements trace

Every requirement with the line in the brief it comes from (`B:<line>` refers to
`sources/cloud_quantum_seeded_monte_carlo.md`). Status and evidence are filled in as the build progresses.
Requirement IDs match `docs/PRD.md`.

| ID | Requirement | Source | Status | Evidence |
|----|-------------|--------|--------|----------|
| FR-1 | Job submission API: POST /jobs validates input, fetches one Qrypt block, derives 256-bit master seed, writes job record (seed hex, params, QUEUED), enqueues one SQS message per shard | B:139-144 | | |
| FR-2 | Shard seeds derived deterministically from master seed + shard index; committed test for distinctness and determinism | B:145-150 | | |
| FR-3 | SQS workers write {sum, sum_sq, n} per shard; aggregation to estimate, SE, 95% CI; GET /jobs/{id} shows progress then COMPLETE | B:151-156 | | |
| FR-4 | 1M-path estimate within 3 SE of Black-Scholes for S0=100, K=100, r=0.05, sigma=0.2, T=1 (committed test + deployed run) | B:157-160 | | |
| FR-5 | POST /jobs/{id}/replay gives a bit-identical estimate | B:161-163 | | |
| FR-6 | Budget (~$1/month) with email/SNS alert; custom metrics (jobs submitted, paths simulated, entropy KiB, shard failures); alarms for worker errors and DLQ depth > 0; forced failure trips DLQ alarm and notifies | B:164-168 | | |
| FR-7 | GET /jobs returns an empty list on a fresh deployment | B:206-207 | | |
| FR-8 | GET /jobs/{id} unknown id returns 404 with a clear message | B:207-208 | | |
| FR-9 | GET /health checks DynamoDB and SSM reachability | B:256 | | |
| ST-1 | Stretch: Step Functions orchestration with retry and wait-for-completion | B:172 | | |
| ST-2 | Stretch: CloudWatch dashboard for job and entropy metrics | B:173 | | |
| ST-3 | Stretch: PENDING_ENTROPY queued retry with backoff | B:174-175 | | |
| ST-4 | Stretch: Checkov or tfsec scan in CI with justified suppressions | B:176 | | |
| ST-5 | Stretch: portfolio Value-at-Risk workload | B:177 | | |
| ST-6 | Stretch: ephemeral per-branch environments (brief says GitHub Actions) | B:178-179 | | |
| ST-7 | Stretch: per-job cost attribution (GB-seconds, request count) in job result | B:180-181 | | |
| EC-1 | Qrypt 401/403/429/500/503/timeout: job rejected with named cause; never seeded locally or from time | B:188-190 | | |
| EC-2 | Duplicate SQS delivery: idempotent conditional put on job_id + shard_index; no double counting | B:191-192 | | |
| EC-3 | Worker failure after retries goes to DLQ; job PARTIAL with failed shard indexes, never COMPLETE with wrong total | B:193-195 | | |
| EC-4 | Shard size bounded under Lambda timeout; oversized paths/shards rejected at submit | B:196-197 | | |
| EC-5 | Burst of submissions stays under Qrypt 30 requests / 10 s | B:198-199 | | |
| EC-6 | Reserved concurrency on workers and maximum paths per job; over-limit rejected | B:200-201 | | |
| EC-7 | Invalid inputs (non-positive sigma, T, paths; shards > paths; non-numeric) return 400 with a clear message | B:202-203 | | |
| EC-8 | terraform destroy removes everything; second plan after apply shows no drift | B:204-205 | | |
| EC-9 | Empty/first run: GET /jobs empty list; unknown id 404 | B:206-208 | | |
| NFR-1 | Submit latency < 800 ms p95 warm; 50 scripted submissions, report p50/p95 | B:214 | | |
| NFR-2 | 1,000,000 paths in < 60 s, submit to COMPLETE, 5 runs | B:215 | | |
| NFR-3 | $0 steady-state at 100 jobs/day of 1M paths; arithmetic shown | B:216 | | |
| NFR-4 | terraform apply from empty < 10 min | B:217 | | |
| SEC-1 | QRYPT_API_KEY as SSM SecureString created out-of-band, not a Terraform variable; reason documented | B:234-236 | | |
| SEC-2 | One IAM role per function, least privilege, no wildcard actions or resources | B:237-238 | | |
| SEC-3 | Function URL with AWS_IAM or bearer key checked against SSM; no anonymous submission | B:239-240 | | |
| SEC-4 | DynamoDB and SQS encryption at rest; TLS in transit | B:241-242 | | |
| SEC-5 | Structured logs with job id, no tokens in logs, explicit retention (e.g. 14 days) | B:243-244 | | |
| SEC-6 | All inputs validated server-side | B:245 | | |
| CQ-1 | Coverage >= 80% on simulation, seeds, aggregation, validation | B:249-250 | | |
| CQ-2 | Terraform modules api, workers, data, observability, budget; documented variables/outputs; fmt and validate clean; one root module + reusable modules; local state OK | B:126-127, B:251-252 | | |
| CQ-3 | Thin handlers; pure simulation and aggregation functions testable without AWS | B:253-254 | | |
| CQ-4 | Graceful degradation; no unhandled exceptions in handlers | B:255 | | |
| CQ-5 | CI runs unit tests, linter, terraform validate, tflint on every push (any free CI) | B:132-133, B:257 | | |
| CQ-6 | Function language one of Python/TS/Go/Rust; dependencies within Lambda package limits | B:128-129 | | |
| CQ-7 | Correctness by committed tests: closed form, seed determinism/uniqueness, bit-identical replay, idempotent aggregation | B:219-228 | | |
| CQ-8 | Always-free services only; no NAT, load balancer, EC2, RDS, Secrets Manager; Function URLs not API Gateway; provisioned DynamoDB; SQS long polling | B:99-119 | | |
| CQ-9 | Live Qrypt usage <= 10 MB total; token never committed; stored as QRYPT_API_KEY in local .env | B:64-67, B:94-97 | | |
| D-1 | Repository with README (GitLab instead of GitHub) | B:267 | | |
| D-2 | AI_USAGE.md: tools, purposes, prompts/configuration that shaped the solution | B:259-263, B:267 | | |
| D-3 | .env.example and a mock Qrypt client so tests run without a token | B:268-269 | | |
| D-4 | Architecture diagram (image or Mermaid) showing every AWS resource and data flow | B:270-271 | | |
| D-5 | Grader quick-start: AWS credentials, SSM parameter, terraform apply, submit, replay, destroy | B:272-273 | | |
| D-6 | Cost note with free-tier arithmetic and Budget configuration screenshot | B:274-275 | | |
| D-7 | Deployed endpoint URL kept up through grading, then destroyed | B:276 | | |
| D-8 | One-line project description <= 120 characters | B:277-278 | | |
| D-9 | Demo video <= 5 min: terraform apply, job to completion, Black-Scholes comparison, bit-identical replay, DLQ alarm firing | B:279-280 | | |
| D-10 | Benchmark report with measured p50/p95, wall-clock, cost arithmetic, rebuild time | B:210-217 | | |
| PRE-1 | Before the timebox: AWS account with billing alerts, working Qrypt token, Terraform and AWS CLI installed and authenticated | B:10-13 | | |
