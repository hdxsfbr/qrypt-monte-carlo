# Research

Research done on 22 October 2026 before any design or build work. Each finding has a source. Labels:
**[Doc]** official documentation or pricing page, **[Brief]** the project brief, **[Live]** a small check we
ran ourselves, **[Est]** our own estimate (with the arithmetic shown).

Terms used below:
- **Lambda**: AWS's run-code-on-demand service. You pay per request and per *GB-second* (memory in GB times
  run time in seconds).
- **Function URL**: a built-in HTTPS address for one Lambda function, used here instead of API Gateway.
- **SQS**: Simple Queue Service, AWS's message queue. **DLQ** (dead-letter queue): a side queue that
  receives messages that failed too many times.
- **DynamoDB**: AWS's key-value database. **RCU/WCU**: read/write capacity units, the throughput you
  reserve on a *provisioned* table.
- **SNS**: Simple Notification Service, used to send alert emails.
- **CloudWatch**: AWS's metrics, alarms and logs service.
- **SSM Parameter Store**: AWS Systems Manager's settings store. A *SecureString* is an encrypted setting.
- **KMS**: Key Management Service, which holds the encryption keys.
- **Terraform state**: the file where Terraform records what it created. Anything passed as a Terraform
  variable ends up in it in plain text.

## 1. AWS Free Tier: what is free, and what changed

### The July 2025 change
- Since 15 July 2025, **new** accounts choose a *Free plan* (up to $200 of credits, account closes after
  6 months or when credits run out) or a *Paid plan*. Old "12 months free" offers no longer apply to new
  accounts. **[Doc]** https://aws.amazon.com/free/
- **Always-free** allowances still apply every month on both plans and do not expire. **[Doc]** same page.

### Which plan is this account on? **[Live]**
- Account `788792938287`, IAM user `hdx`, default region `us-east-1`.
- It has Lambda functions last modified in **2016**, so it predates the change. It is a **legacy paid
  account**, not on the new credit-based Free plan. The Free plan status call
  (`aws freetier get-account-plan-state`) returned "Missing data for account", which is what a legacy
  account returns.
- `aws freetier get-free-tier-usage` shows **Always Free** usage lines (CloudWatch, SNS, Glue), confirming
  always-free allowances are being applied to this account.
- **Consequence:** anything over an always-free allowance is billed in real dollars, not taken from
  credits. There are no credits to absorb a mistake.

### Always-free monthly allowances (verified)

| Service | Always-free allowance | Notes | Source |
|---------|----------------------|-------|--------|
| Lambda | 1,000,000 requests + 400,000 GB-seconds | Counted across all regions | **[Doc]** https://aws.amazon.com/free/serverless/ |
| DynamoDB | 25 GB storage + 25 provisioned WCU + 25 provisioned RCU | Only *provisioned* capacity is free; on-demand requests are not in the allowance | **[Doc]** https://aws.amazon.com/free/serverless/ |
| SQS | 1,000,000 requests | Every API call is a request, including empty polls; each 64 KB of payload counts as one request | **[Doc]** https://aws.amazon.com/sqs/pricing/ |
| SNS | 1,000,000 publishes, 100,000 HTTP/S deliveries, 1,000 email deliveries | | **[Doc]** https://aws.amazon.com/free/application-integration/ |
| CloudWatch | 10 custom metrics, 10 alarm metrics, 1,000,000 API requests, 5 GB logs (ingest + archive + Logs Insights scanned), 3 dashboards of up to 50 metrics | Each unique metric name + dimension combination is a separate metric; extra metrics cost $0.30 each per month | **[Doc]** https://aws.amazon.com/cloudwatch/pricing/ |
| Step Functions | 4,000 state transitions | Only relevant to a stretch goal | **[Doc]** https://aws.amazon.com/free/serverless/ |
| SSM Parameter Store (Standard) | No charge for standard parameters | SecureString uses the AWS-managed KMS key `aws/ssm`; that key has no monthly fee | **[Brief]**, KMS pricing |
| AWS Budgets | Budget monitoring and alerts are free; first 2 *action-enabled* budgets are free | Budgets are checked about once a day, so alerts can lag by up to 24 hours | **[Doc]** https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/ |
| Lambda Function URLs | No separate charge; you pay only for the Lambda invocation | | **[Doc]** Lambda pricing |

### What already uses the account **[Live]** (read-only checks)
- **Spend this month (1 to 22 October): $1.01, all of it Amazon Route 53** (domain name hosting, about
  $0.50 per hosted zone per month). Everything else was within free allowances.
- **CloudWatch alarms:** 1 existing alarm (`BillingAlarm`, threshold $100, notifying SNS topic `NotifyMe`).
  That leaves 9 of the 10 free alarms.
- **SNS topics:** 2 existing (`NotifyMe`, `ww-breakfast-dev`). SNS usage in us-west-2 this month: about
  36,700 requests, well inside the 1M allowance.
- **Lambda:** 2 old functions from 2016 (`t1`, `PublishSNSTest`). Account concurrency limit is **1,000**
  (unreserved 1,000), so we can set reserved concurrency without a quota request.
- **DynamoDB, SQS:** none in us-east-1, so the full 25 RCU / 25 WCU and 1M SQS requests are ours.
- **Budgets:** none exist. **SSM parameters:** none exist in us-east-1.
- Cost Explorer checks themselves cost $0.01 each; we made three (about $0.03 total).

### Free-tier risks found
1. **A $1/month account-wide budget would alert every month**, because Route 53 already costs about $1.01.
   Fix: filter the budget to the services this project uses (Lambda, DynamoDB, SQS, SNS, CloudWatch, SSM,
   KMS). A tag-based filter is cleaner but needs a cost-allocation tag activated in the billing console
   first and takes up to 24 hours to show data.
2. **Idle SQS polling.** When a Lambda function reads from SQS, AWS polls the queue all the time, even when
   it is empty: 2 to 5 pollers, each making about 3 long-poll calls a minute. Idle cost:
   5 × 3 × 60 × 24 × 30 = **648,000 requests a month**, about two-thirds of the 1M free SQS requests,
   before any real work. **[Doc]** https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html ,
   https://repost.aws/questions/QUw66hGkRwSWiBSjkIJhTgOw . Setting a *maximum concurrency* on the queue
   trigger turns off AWS's "scale down to 2 pollers" optimisation, so it can make idle polling worse.
   Mitigation: keep one worker queue (the DLQ has no reader), show the arithmetic, and destroy the stack
   after grading.
3. **DynamoDB on-demand is not free.** Use provisioned capacity, at most 25 RCU / 25 WCU in total across
   every table *and* index in the region.
4. **Custom metrics are counted per dimension combination.** Adding a per-job dimension would create a
   new paid metric for every job. Keep a single fixed dimension set.
5. **Log storage.** Lambda keeps logs forever unless a retention is set; set 14 days on every log group.
6. **Cost Explorer API calls cost $0.01 each**; use them sparingly in scripts.

## 2. Qrypt quantum entropy API

- Endpoint `GET https://api-eus.qrypt.com/api/v1/quantum-entropy?size={n}`, `n` in KiB from 1 to 512.
  Headers `Accept: application/json` and `Authorization: Bearer <token>`. Response
  `{"random": ["<base64 of 1,024 bytes>", ...], "size": n}`. **[Brief]**, https://docs.qrypt.com/eaas/
- Rate limit: 30 requests per 10 seconds per token (429 above that). **[Brief]**
- Assessment budget: at most 10 MB (10,240 KiB) of entropy across the whole assessment. One 1 KiB call per
  job is enough (a 256-bit seed needs 32 bytes). **[Brief]**
- Lessons from Andre's earlier Qrypt work (`qrypt-quickstart`, docs/claims-to-source.md), checked live
  there:
  - a **wrong token returns 403**, not 401; 401 only means a missing or malformed `Authorization` header;
  - 403 also means the entropy allotment for the period is used up, so the error message must say
    "token rejected or quota reached";
  - Qrypt's edge network (Cloudflare) **blocks the default Python `urllib` User-Agent** with a 403
    ("Error 1010"). The client must send its own User-Agent.

### Live checks **[Live]** (22 October 2026, about 1:20 PM CT)
Token loaded from the existing local `.env` into memory only; never printed.

| Call | Result |
|------|--------|
| 1 KiB, default Python `urllib` User-Agent | **403** in 178 ms (the Cloudflare User-Agent block above; no entropy returned) |
| 1 KiB, custom User-Agent `qrypt-monte-carlo-research/0.1` | **200** in 541 ms; 1 block of exactly 1,024 bytes; response keys `random`, `size`; `size` = 1 |

- The existing token **still works**. Entropy used so far by this project: **1 KiB** (the blocked call
  returned nothing).
- 541 ms was measured from the lab on a home connection, including a fresh TLS (encrypted connection) handshake.
  From us-east-1 (Virginia) with a reused connection it should be much lower, but the Qrypt call will be
  the biggest part of submit latency. Measured, not assumed, in the build.

## 3. Function URL authentication

| Option | How a caller authenticates | How a grader calls it | Notes |
|--------|---------------------------|----------------------|-------|
| `AWS_IAM` | Each request is signed with AWS credentials (Signature Version 4) | Needs AWS credentials in the same account (or a cross-account grant), then a signing tool such as `awscurl`, Postman, or a small Python script using botocore | Strongest. Fine when the grader deploys in their own account; awkward for a grader calling *our* deployed URL, since they have no credentials in our account |
| `NONE` + bearer key checked against SSM | Header `Authorization: Bearer <key>`; the function compares it (constant-time) with a SecureString in SSM | Plain `curl` | Allowed by the brief ("a bearer key validated against SSM"). Each unauthenticated hit still costs one Lambda request, so reserved concurrency caps abuse |

- **Change since October 2025:** a new Function URL with auth `NONE` needs **two** resource-policy
  statements, `lambda:InvokeFunctionUrl` *and* `lambda:InvokeFunction` (the second limited with
  `lambda:InvokedViaFunctionUrl = true`). Terraform must create both or callers get 403.
  **[Doc]** https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html
- Function URLs answer only on HTTPS (TLS in transit is automatic). **[Doc]**
  https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html

## 4. Lambda runtime, speed, memory

- Runtimes: `python3.13` and `python3.14` are both supported on Amazon Linux 2023 until June 2029.
  **[Doc]** https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html . The lab and CI use Python
  3.13, so `python3.13` keeps local tests and the cloud identical.
- Package limits: 50 MB zipped upload, 250 MB unzipped including layers. **[Live]** `get-account-settings`.
- CPU scales with memory; at 1,769 MB a function gets one full virtual CPU. Plain Python runs on one core,
  so more memory than that does not speed it up. **[Doc]** Lambda memory configuration docs.
- **Speed test on the lab [Live]** (Intel i9-14900KF, Python 3.13, NumPy 2.1.2):

  | Workload | Time on the lab |
  |----------|-----------------|
  | 100,000 paths, plain Python (`random` + `math`) | 0.036 s |
  | 100,000 paths, NumPy | 0.018 s |
  | 1,000,000 paths, NumPy, one process | 0.018 s |
  | Same 1M NumPy run: estimate 10.4276, standard error 0.0147; Black-Scholes 10.4506 | within 1.6 standard errors |

  **[Est]** A Lambda core is roughly 2 to 3 times slower than this desktop chip, so plain Python should do
  1,000,000 paths in about 1 second of total compute, split across shards. Wall-clock time will be
  dominated by queue pickup and cold starts (a few seconds), far under the 60-second target.
- **NumPy cost:** NumPy is not in the Lambda Python runtime; it needs a layer (an add-on package) of
  roughly 25 to 35 MB unzipped, and importing it adds a few hundred milliseconds to each cold start.
- **Reproducibility:** NumPy's `Generator` does **not** promise the same numbers across NumPy versions
  (only the frozen legacy `RandomState` does). **[Doc]**
  https://numpy.org/doc/stable/reference/random/generator.html . Python's own `random` module promises
  that `random()` gives the same sequence for the same integer seed across versions; its `gauss()` does
  not carry that promise, so we would write our own normal-number step on top of `random()`.
  **[Doc]** https://docs.python.org/3/library/random.html#notes-on-reproducibility
- **Conclusion:** plain Python (standard library only) is fast enough, keeps packages tiny and cold starts
  short, and gives a firmer replay guarantee. NumPy stays a fallback if measured speed disappoints.

## 5. Deriving shard seeds and bit-identical replay

| Method | What it is | Pros | Cons |
|--------|-----------|------|------|
| `numpy.random.SeedSequence(master).spawn(n)` | NumPy's built-in way to split one seed into independent child seeds | The brief's own example; well studied | Needs NumPy; child streams can change between NumPy versions |
| HKDF-SHA256 (RFC 5869) | A standard key-derivation function: hashes the master seed with a label and the shard number to get a new 256-bit seed | Standard library only (`hmac`, `hashlib`); has official test vectors; the same inputs always give the same output | We write about 15 lines and must test them |

- Sources: https://numpy.org/doc/stable/reference/random/bit_generators/generated/numpy.random.SeedSequence.html ,
  https://www.rfc-editor.org/rfc/rfc5869
- **Bit-identical replay needs all of these to be the same:** master seed, parameters, shard count, the
  derivation label/version, the random generator, the floating-point code path, the runtime version, and
  the order in which shard totals are added up. So we store an algorithm version and the runtime with each
  job, and always combine shards in shard-index order with exact summation (`math.fsum`).

## 6. Reliability: duplicates, retries, dead letters, concurrency

- **SQS standard queues can deliver a message more than once.** Idempotent writes fix this: a DynamoDB
  conditional write (`attribute_not_exists`) only succeeds the first time for a given
  `job_id + shard_index`; a repeat gets `ConditionalCheckFailed`, which the worker treats as "already
  done". **[Doc]** DynamoDB condition expressions.
- **Counting completed shards safely:** a DynamoDB transaction (`TransactWriteItems`) can write the shard
  result *and* add 1 to the job's completed count in one all-or-nothing step, so a redelivered message
  can never count twice. Transactions use twice the normal write capacity. **[Doc]** DynamoDB transactions.
- **Retries and DLQ:** the queue's redrive policy moves a message to the DLQ after `maxReceiveCount`
  failed receives. AWS recommends a queue visibility timeout of at least 6 times the function timeout.
  The worker can read `ApproximateReceiveCount` to know it is on the last attempt. **[Doc]**
  https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html
- **Concurrency:** *reserved concurrency* caps how many copies of a function can run at once (a cost and
  overload cap). With an SQS trigger, the trigger's *maximum concurrency* (minimum 2) stops Lambda from
  throttling and needlessly pushing messages toward the DLQ; it should be set at or below the reserved
  concurrency. **[Doc]** https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html
- **DLQ alarm:** alarm on the DLQ's `ApproximateNumberOfMessagesVisible > 0`. Nothing should read the DLQ
  automatically, or the alarm may never see a message.

## 7. Region
- `us-east-1` (N. Virginia): already the configured default; AWS Budgets and billing data live there;
  and Qrypt's `api-eus` endpoint is in the US East, so it should be the closest region to Qrypt.

## 8. Tooling installed on the lab [Live]
- Terraform 1.17.0 and TFLint 0.65.0 in `~/.local/bin` (checksums verified); Checkov 3.3.30 through
  `pipx`. AWS CLI 2.32.17, already signed in. No `sudo` used.

## Brief versus portal page
The portal page shows the same project as the attached brief and adds the metadata in
`sources/portal-page.md` (Silver tier label, program contact Sean Neal). Details that are only in the
attached brief:
- the three user groups (quant analysts, platform operators, auditors) and the business case numbers;
- the setup work that does not count against the 2 days (AWS account with billing alerts, Qrypt token,
  Terraform and AWS CLI installed);
- the full Qrypt error table and the **10 MB total entropy budget**;
- the free-tier table, the "do not use" list (NAT gateways, load balancers, EC2, RDS, Secrets Manager) and
  "use provisioned DynamoDB" and "use SQS long polling";
- the exact API shapes (`POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/replay`,
  `GET /health`), statuses (`QUEUED`, `COMPLETE`, `PARTIAL`, `PENDING_ENTROPY`) and the edge-case list;
- benchmark measurement methods, including **environment rebuild under 10 minutes** and **$0 at 100 jobs
  a day**;
- the security list (secret created out-of-band, no wildcard IAM, encryption at rest, 14-day logs);
- the stretch list (Step Functions, dashboard, `PENDING_ENTROPY` retry, Checkov/tfsec, Value-at-Risk,
  ephemeral environments, per-job cost);
- submission items: `AI_USAGE.md`, `.env.example`, mock Qrypt client, diagram, grader quick-start, cost
  note with a **Budget screenshot**, a one-line description of at most 120 characters, and what the video
  must show; and the **100-point rubric** (pass at 70).
- The brief says "Tier: Mid" where the portal says "Silver", and says "GitHub repository" and "GitHub
  Actions"; this project is hosted on GitLab (CI on GitLab).
