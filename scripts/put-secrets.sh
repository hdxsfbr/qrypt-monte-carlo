#!/usr/bin/env bash
# Copy the two secrets from .env into AWS SSM Parameter Store (encrypted "SecureString" parameters),
# where the API function reads them. Terraform never sees the values, so they never enter its state.
#
# usage: scripts/put-secrets.sh [--dry-run] [--env-file PATH] [--environment NAME]
#   --dry-run        check everything and list what would be written, but write nothing
#   --env-file       file with QRYPT_API_KEY=... and API_KEY=... lines (default: .env)
#   --environment    deployment name used in the parameter path (default: dev -> /qmc/dev/...)
#
# Safety:
# - It refuses to run unless the AWS profile (default "qmc") belongs to the project account.
# - The .env file is read line by line, never executed.
# - Values are never printed and never placed on a command line (where other users could see them in
#   the process list). They go into a private temporary file that is deleted on exit.
set -euo pipefail

EXPECTED_ACCOUNT="144249522427"
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-qmc}"
ENV_FILE=".env"
ENVIRONMENT="dev"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --env-file) ENV_FILE="${2:?--env-file needs a path}"; shift ;;
    --environment) ENVIRONMENT="${2:?--environment needs a name}"; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$PROFILE" != "qmc" ]; then
  echo "refusing: AWS profile is '$PROFILE'; this project only uses the 'qmc' profile" >&2
  exit 1
fi
[[ "$ENVIRONMENT" =~ ^[a-z0-9-]+$ ]] || { echo "environment must be lowercase letters, digits or -" >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE (copy .env.example and fill it in)" >&2; exit 1; }

# Read KEY=VALUE without running the file. Surrounding quotes are removed.
read_value() {
  local key="$1" line value=""
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "$key="*) value="${line#"$key="}" ;;
    esac
  done < "$ENV_FILE"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then value="${value:1:${#value}-2}"; fi
  printf '%s' "$value"
}

account=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text) || {
  echo "could not confirm the AWS account; if the session expired run: aws login --remote --profile qmc" >&2
  exit 1
}
if [ "$account" != "$EXPECTED_ACCOUNT" ]; then
  echo "refusing: profile '$PROFILE' is account $account, not the project account $EXPECTED_ACCOUNT" >&2
  exit 1
fi

tmp=$(mktemp)
chmod 600 "$tmp"
trap 'rm -f "$tmp"' EXIT

status=0
for pair in "QRYPT_API_KEY:/qmc/$ENVIRONMENT/qrypt_api_key" "API_KEY:/qmc/$ENVIRONMENT/api_key"; do
  key="${pair%%:*}"
  name="${pair#*:}"
  value=$(read_value "$key")
  if [ -z "$value" ] || [[ "$value" == replace-with-* ]]; then
    echo "skip $name: $key is empty or still the example placeholder in $ENV_FILE" >&2
    status=1
    continue
  fi
  if [ "$key" = "API_KEY" ] && [ "${#value}" -lt 32 ]; then
    echo "skip $name: API_KEY must be at least 32 characters" >&2
    status=1
    continue
  fi
  if [ "$DRY_RUN" = 1 ]; then
    echo "dry run: would write $name (SecureString, ${#value} characters) in $REGION"
    continue
  fi
  # The value travels to python on standard input and from there into the private file.
  printf '%s' "$value" | python3 -c '
import json, sys
json.dump({"Name": sys.argv[1], "Type": "SecureString", "Overwrite": True, "Value": sys.stdin.read()},
          open(sys.argv[2], "w"))' "$name" "$tmp"
  aws ssm put-parameter --profile "$PROFILE" --region "$REGION" \
    --cli-input-json "file://$tmp" --query Version --output text >/dev/null
  : > "$tmp"
  echo "wrote $name"
done
exit "$status"
