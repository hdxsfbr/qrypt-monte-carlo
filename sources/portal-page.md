# Portal page: Quantum-Seeded Monte Carlo Platform on AWS

- **Source:** https://portal.gauntletai.com/projects/oGA3nSogqIAj9zwROy36 (Gauntlet portal, sign-in required)
- **Captured:** Thursday 22 October 2026, about 12:52 PM CT (US Central Time), read in a signed-in browser
- **Company:** Qrypt
- **Tier shown on the portal:** Silver
- **Timebox:** 2 days
- **Program contact:** Sean Neal
- **Attachment:** `cloud_quantum_seeded_monte_carlo.md` (saved next to this file, unchanged). It is the full brief.

> Note: the portal needs a login, so this file is a faithful summary of what the page showed rather than a
> byte-for-byte copy. The attached brief is the authoritative, complete text. If the two ever disagree, the
> difference is listed in `docs/research.md` under "Brief versus portal page".

## What the page asks for (summary)

Build a **Quantum-Seeded Monte Carlo Platform on AWS**. Monte Carlo means estimating a number (here, the
fair price of a stock option) by simulating many random outcomes and averaging them.

- **Workload:** price one European call option under the Black-Scholes model (the textbook option-pricing
  formula, so the right answer is known).
- **Fan-out:** a job is split into chunks ("shards") that run in parallel on AWS Lambda (run-code-on-demand).
  Amazon SQS (a message queue) hands out the shards; results are combined in Amazon DynamoDB (a database).
- **Quantum seed:** each job's master random seed comes from Qrypt quantum entropy. Each shard's seed is
  derived from that master seed, so any past job can be replayed with exactly the same answer.
- **Infrastructure:** everything is created with Terraform (infrastructure as code). Stay inside AWS
  always-free allowances, with a budget alarm and alerts when jobs fail. No API Gateway, EC2 or Secrets
  Manager; the Qrypt key is stored in AWS Systems Manager (SSM) Parameter Store.
- **Proof needed:** at 1,000,000 paths the price lands within 3 standard errors of the exact formula, in
  under 60 seconds. Submitting a job answers in under 0.8 seconds for 95% of requests (warm). Test coverage
  of at least 80%.
- **Submission:** the repository with its docs, a deployed endpoint, and a demo video of 5 minutes or less.
