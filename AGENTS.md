# Working in this repository (for coding agents)

## Ground rules
- Read `docs/PRD.md`, `docs/DESIGN.md` and `docs/REQUIREMENTS_TRACE.md` before changing anything.
- Do not start build work or create AWS resources until the design is approved by the repository owner.
- Commit small and often, with clear messages. Push after each logical step.
- Update `README.md` (status table) and `docs/REQUIREMENTS_TRACE.md` (status and evidence) when a requirement moves.

## Secrets
- Never read, print, echo or log `.env`, environment variables that hold keys, SSM parameter values, or
  HTTP `Authorization` headers.
- The Qrypt token (`QRYPT_API_KEY`) and the API bearer key live only in a local `.env` (git-ignored) and in
  SSM Parameter Store, created out-of-band with the AWS CLI. Never pass them as Terraform variables: they
  would be written to Terraform state.
- Tests use the mock Qrypt client and need no token. Live Qrypt calls are limited: one 1 KiB call per job,
  and the whole assessment must stay under 10 MB of entropy.

## AWS account
- All project AWS work uses the dedicated Free plan account `144249522427` through the CLI profile `qmc`
  (`export AWS_PROFILE=qmc`, region `us-east-1`). Never use the default profile: it points at an older,
  unrelated account.
- The `qmc` login is a browser session that expires after some hours. If a command fails with expired
  credentials, stop and ask the owner to run `aws login --remote --profile qmc`.

## Cost
- Stay inside AWS always-free allowances. Do not create NAT gateways, load balancers, EC2, RDS, API Gateway,
  Secrets Manager, or Step Functions without approval.
- `terraform destroy` must remove everything; a second `terraform plan` after apply must show no changes.

## Code layout (planned)
- `src/qmc/`: pure Python (simulation, seeds, aggregation, validation, Qrypt client). No AWS calls here.
- `src/handlers/`: thin Lambda handlers that wire the pure code to AWS.
- `infra/`: Terraform root module plus modules `api`, `workers`, `data`, `observability`, `budget`.
- `tests/`: pytest; coverage must stay at or above 80%.

## Checks to run before pushing
`make check` (unit tests with coverage, lint, `terraform fmt -check`, `terraform validate`, `tflint`).
