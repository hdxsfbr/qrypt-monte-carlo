# Milestone M2 live checks, 22 October 2026

These are the first checks against the real deployment in AWS account `144249522427` (region `us-east-1`).
All times are US Central Time (CT). Every file here is real command output; no secret appears in any of
them (the scripts never print the Qrypt token or the API key).

Terms used below:

- **Shard:** one piece of a job, run by one worker function.
- **Standard error (SE):** how much the estimate would typically move if the job were run again with new
  randomness. "Within 3 SE" means the gap to the exact answer is less than three of these units.
- **Black-Scholes price:** the exact price from the formula, 10.450583572185565 for these inputs.
- **Bit-identical:** the two answers are the same 64-bit number down to the last bit, shown here as
  `estimate_hex` (the number written in hexadecimal so nothing is rounded away).
- **DLQ (dead-letter queue):** where a shard's message goes after three failed attempts.
- **PARTIAL:** a job where at least one shard failed; it shows which shards and gives no result.

## Results

| Check | Result | File |
|-------|--------|------|
| Deploy | `terraform apply` created 25 resources in about 84 seconds (4:44 PM CT). A second `terraform plan` afterwards shows no changes. | `terraform-plan-summary.txt`, end of `checks.txt` |
| Secrets | Both SSM parameters stored as SecureString (version 1). Neither value is in the Terraform state file (checked by searching the state for each value). | `checks.txt` |
| Logs | All 190 log lines from both functions so far are JSON; a search of them finds neither secret value and no `Bearer` header. | (search run on the lab; nothing to save) |
| Health | `GET /health`: DynamoDB ok, SSM ok. | `checks.txt` |
| Access control | Requests with no API key or a wrong one get 401. | `checks.txt` |
| 1,000,000 paths, 10 shards | Estimate 10.451834830458662, SE 0.014717, 95% range 10.42299 to 10.48068. Gap to Black-Scholes: 0.085 SE, so well within 3 SE. Job created 4:45:57.864 PM CT, finished 4:45:59.510 PM CT (1.6 seconds). | `job-1m-paths.json` |
| Replay | Same seed, no Qrypt call; `bit_identical: true`, both `0x1.4e756e51806fep+3`. | `replay.json` |
| Same seed on a laptop | `scripts/qmc local` with the job's seed gives the same `0x1.4e756e51806fep+3`. | `local-rerun.json` |
| Forced shard failure | Job with 4 shards, shard 2 told to fail (demo switch on for this test only). Shard 2 was tried 3 times, then marked FAILED; the job ended PARTIAL with `failed_shards: [2]` and no result. The message went to the DLQ. | `forced-failure-job.json`, `dlq-message.json` |
| DLQ alarm | `qmc-dev-dlq-depth` went OK to ALARM at 4:55:24 PM CT (1 message in the DLQ), and back to OK at 4:58:24 PM CT after the one test message was deleted. | `checks.txt` |
| Demo switch off again | Re-applied with `enable_fault_injection = false`; a request using `fail_shards` now gets 400 and no Qrypt call is made. | `checks.txt` |
| Metrics | In CloudWatch, namespace `QMC`: JobsSubmitted 3, PathsSimulated 2,075,000, EntropyKiB 2, ShardFailures 1, ShardDurationMs present. QryptErrors has no data because no Qrypt call has failed; CloudWatch only lists a metric once it has a value. | `checks.txt` |
| Budget | `qmc-dev-monthly`: cost budget, $1.00 per month, actual spend $0.00, alerts at 50% and 100% actual and 100% forecast. | `checks.txt` |
| Alert emails | The SNS email subscription is "PendingConfirmation" until the confirmation link in AWS's email is clicked. Until then alarms change state but no email arrives. | `checks.txt` |
| Lambda concurrency limit | Still 10. Increase to 1,000 requested at 4:43 PM CT (request `506b0212b9f742e1a8fc7e8d040cb036aWQ1epwL`, AWS support case 179270556400278, status CASE_OPENED). Until it is granted the deployment keeps `reserve_concurrency = false` and `worker_concurrency = 5`. | `checks.txt` |

## Qrypt usage

These checks made two live Qrypt requests, 1 KiB each (2 KiB in total): the 1,000,000-path job and the forced-failure job.
The replay and the rejected request made none. That is far below the 10 MB allowance and the 30 requests per
10 seconds limit.
