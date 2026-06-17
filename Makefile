.PHONY: install-cli install-hub install-all test-cli test-hub test-all lint format hub-build hub-up hub-down hub-full-build sync-roles

# ── CLI (src/agentweave) ─────────────────────────────────────────────────────

install-cli:
	pip install -e ".[dev]"

test-cli:
	pytest tests/ -v --cov=agentweave --cov-report=term-missing

# ── Hub (hub/) ───────────────────────────────────────────────────────────────

install-hub:
	pip install -e "hub/[dev]"

test-hub:
	pytest hub/tests/ -v

# ── Both ─────────────────────────────────────────────────────────────────────

install-all: install-cli install-hub

test-all: test-cli test-hub

# ── Code quality ─────────────────────────────────────────────────────────────

lint:
	ruff check src/
	mypy src/

format:
	black src/ hub/hub/

# ── Docker (Hub) ─────────────────────────────────────────────────────────────

hub-build:
	cd hub && docker compose up --build -d

# Default `hub-up` uses the locally-built `agentweave-hub:audit` image (built
# by `hub-full-build`) so audit-branch code is actually run. Override with
# `make hub-up AW_HUB_IMAGE=ghcr.io/gutohuida/agentweave-hub:latest` to
# use the published release image instead.
hub-up:
	cd hub && docker compose up -d

hub-down:
	cd hub && docker compose down -v

# Sync role templates from CLI source into Hub package so they are bundled in Docker builds
sync-roles:
	mkdir -p hub/hub/data/roles
	cp src/agentweave/templates/roles/*.md hub/hub/data/roles/
	cp src/agentweave/templates/roles/roles.json hub/hub/data/roles/roles.json

hub-full-build: sync-roles
	cd hub && docker build . -t agentweave-hub:audit
	# Belt-and-braces: also let docker compose build the same image under its
	# own tag (hub-hub) in case someone prefers `docker compose up --build`.
	cd hub && docker compose -f docker-compose.yml -f docker-compose.build.yml build
