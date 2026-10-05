# Company overlay: do not modify upstream Cargo profiles to release this engine.
PYTHON ?= python3
VERSION ?=
export VERSION
export CARGO_BUILD_JOBS ?= 2
AGENT_COMMAND = "$(PYTHON)" company/agent-server/commands.py

.DEFAULT_GOAL := help
.PHONY: help build smoke package test build-ci release release-status
help:
	@$(AGENT_COMMAND) help
build:
	@$(AGENT_COMMAND) build
smoke:
	@$(AGENT_COMMAND) smoke
package: build smoke
	@$(AGENT_COMMAND) package
test:
	@$(PYTHON) -m unittest discover -s company/agent-server/tests -v
build-ci:
	@$(AGENT_COMMAND) build-ci
release:
	@$(AGENT_COMMAND) release
release-status:
	@$(AGENT_COMMAND) release-status
