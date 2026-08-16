.PHONY: install-cli install-hub install-all test-cli test-hub test-all lint format format-check hub-build hub-up hub-down hub-full-build sync-skills ui ui-check

# ── CLI (src/agentweave) ─────────────────────────────────────────────────────

install-cli:
	pip install -e ".[dev]"

test-cli:
	pytest tests/ -v --cov=agentweave --cov-report=term-missing

# ── Hub (hub/) ───────────────────────────────────────────────────────────────

install-hub:
	pip install -e "hub/[dev]"

test-hub:
	pytest hub/tests/ -n auto

# ── Both ─────────────────────────────────────────────────────────────────────

install-all: install-cli install-hub

test-all: test-cli test-hub

# ── Code quality ─────────────────────────────────────────────────────────────

lint:
	ruff check src/ hub/ tests/
	mypy src/

format:
	black src/ hub/hub/ hub/tests/ tests/

format-check:
	black --check src/ hub/hub/ hub/tests/ tests/

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

# Mirror hand-written dev skills from .claude/skills/ out to the agents that can't read it:
# .agents/skills/ (Kimi) and ~/.codex/skills/ (Codex — user-level only, it has no
# project-level discovery). Additive; leaves generated aw-* skills at the destination alone.
sync-skills:
	python scripts/sync_skills.py

hub-full-build:
	cd hub && docker build . -t agentweave-hub:audit
	# Belt-and-braces: also let docker compose build the same image under its
	# own tag (hub-hub) in case someone prefers `docker compose up --build`.
	cd hub && docker compose -f docker-compose.yml -f docker-compose.build.yml build

# Copy the built UI into the Hub package and record the source state it was built from.
#
# `hub/hub/static/ui` is a committed build artefact, and `/health` reports when it drifts behind
# `hub/ui/src`. Before the stamp that report could not be cleared by doing what it asked: a change
# that leaves the bundle byte-identical gives the rebuild nothing to commit, so the artefact's
# commit date never moved and the warning stood forever. The stamp is what gives an identical
# rebuild something to commit.
#
#   cd hub/ui && npm run build
#   make ui
#   git add hub/ui/src hub/hub/static/ui && git commit
ui:
	python scripts/refresh_ui_bundle.py

# Verify the committed bundle asserts it was built from the source that is present. Cheap enough
# for CI; the real proof is a job that rebuilds and diffs.
ui-check:
	python scripts/refresh_ui_bundle.py --check
