.PHONY: help clean clean-build clean-pyc clean-test clean-venv lint coverage test synth ls diff install bootstrap-tooling bootstrap-target deploy-pipeline destroy-pipeline
.DEFAULT_GOAL := help

define BROWSER_PYSCRIPT
import os, webbrowser, sys

from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

BROWSER := python -c "$$BROWSER_PYSCRIPT"

ifeq ($(OS),Windows_NT)
	SHELL := powershell.exe
	.SHELLFLAGS := -NoProfile -Command
endif

help:
ifeq ($(OS),Windows_NT)
	foreach($$line in $$(get-content Makefile | Select-String -Pattern "^([a-zA-Z_-]+):.*?## (.*)`$$`$$")) {write-host "$$("{0, -20}" -f $$($$line -split ":")[0]) $$($$($$line -split "##")[-1])"}
else
	@python3 -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)
endif

clean: clean-cdk clean-pyc clean-test ## Remove all build, test, coverage and Python artifacts

clean-cdk: ## Remove cdk artifacts
ifeq ($(OS),Windows_NT)
	Get-ChildItem * -Include cdk/cdk.out -Recurse | Remove-Item  -Force -Recurse -ErrorAction SilentlyContinue;
	Get-ChildItem * -Include cdk/cdk.context.json -Recurse | Remove-Item  -Force -Recurse -ErrorAction SilentlyContinue;
	Get-ChildItem * -Include cdk/package-lock.json -Recurse | Remove-Item  -Force -Recurse -ErrorAction SilentlyContinue;
else
	rm -fr cdk/cdk.out
	rm -f cdk/cdk.context.json
	rm -f cdk/package-lock.json
endif

clean-pyc: ## Remove Python file artifacts
ifeq ($(OS),Windows_NT)
	Get-ChildItem * -Include *.pyc -Recurse | Remove-Item  -ErrorAction SilentlyContinue;
	Get-ChildItem * -Include *.pyo -Recurse | Remove-Item  -ErrorAction SilentlyContinue;
else
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +
endif

clean-test: ## Remove test and coverage artifacts
ifeq ($(OS),Windows_NT)
	Get-ChildItem * -Include .tox* -Recurse | Remove-Item  -ErrorAction SilentlyContinue;
	Get-ChildItem * -Include .coverage* -Recurse | Remove-Item  -ErrorAction SilentlyContinue;
	Get-ChildItem * -Include htmlcov -Recurse | Remove-Item  -Force -Recurse -ErrorAction SilentlyContinue;
	Get-ChildItem * -Include .pytest_cache -Recurse | Remove-Item  -Force -Recurse -ErrorAction SilentlyContinue;
else
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache
endif

poetry-lock: load-codeartifact-settings
ifeq ($(OS),Windows_NT)
	@.\scripts\poetry_pre_commit.ps1 -account $(account) -domain $(domain) -repoName $(repo_name) -region $(region) -command lock
else
	@./scripts/poetry_pre-commit.sh -a $(account) -d $(domain) -r $(repo_name) -p lock
endif

lint: ## Autoformat with black check additional linting with flake8
	pre-commit run lint

security: ## Security scans with pip-audit
	pip-audit
	pre-commit run security

test:
	pytest -v
	pytest --cov=cdk

pre-commit-all:
	pre-commit run --all-files

synth: ## Run cdk synth
	cd cdk; cdk synth

ls: ## Run cdk ls
	cd cdk; cdk ls

diff: ## Run cdk diff
	cd cdk; cdk diff

install:
	poetry install
	pre-commit install

install-ci:
	poetry install

load-pipeline-settings:
	$(eval QUALIFIER = $(shell cd cdk; python -c "from l3constructs.helpers.helper import Helper; import constants; helper = Helper(); print(helper.get_qualifier());"))
	$(eval APP = $(shell cd cdk; python -c "from l3constructs.helpers.helper import Helper; import constants; helper = Helper(); print(helper.get_cdk_app_name().capitalize());"))

bootstrap: load-pipeline-settings ## Bootstrap tooling account
	@echo "Boostrapping for qualifier:$(QUALIFIER)"
	@cd cdk; cdk bootstrap --toolkit-stack-name "$(APP)BootstrapStack" --qualifier "$(QUALIFIER)"
cleanup-bootstrap: load-pipeline-settings
	$(shell python ./scripts/cleanup_cdk_bootstrap.py $(QUALIFIER) "$(APP)BootstrapStack")

deploy: load-pipeline-settings ## Deploy CDK pipeline
	@cd cdk; cdk deploy --progress events --require-approval never

destroy: load-pipeline-settings ## Destroy CDK pipeline
	@cd cdk; cdk destroy  --progress events --force
