# Local checks. `make check` runs what CI runs.
PY ?= python3.13
VENV := .venv
PY_DIRS := $(wildcard src tests scripts)
BIN := $(VENV)/bin
TF_DIR := infra

.PHONY: venv test lint fmt tf-fmt tf-validate tflint checkov check clean

venv: $(BIN)/pytest
$(BIN)/pytest: requirements-dev.txt
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -r requirements-dev.txt
	touch $@

test: venv
	$(BIN)/pytest --cov --cov-report=term-missing --cov-fail-under=80

lint: venv
	$(BIN)/ruff check $(PY_DIRS)
	$(BIN)/ruff format --check $(PY_DIRS)

fmt: venv
	$(BIN)/ruff format $(PY_DIRS)
	terraform -chdir=$(TF_DIR) fmt -recursive

tf-fmt:
	terraform -chdir=$(TF_DIR) fmt -check -recursive

tf-validate:
	terraform -chdir=$(TF_DIR) init -backend=false -input=false >/dev/null
	terraform -chdir=$(TF_DIR) validate

tflint:
	cd $(TF_DIR) && tflint --init >/dev/null && tflint --recursive --config "$$(pwd)/.tflint.hcl"

checkov:
	checkov -d $(TF_DIR) --quiet --compact --framework terraform

check: lint test tf-fmt tf-validate tflint checkov

clean:
	rm -rf $(VENV) .pytest_cache .coverage .ruff_cache build
