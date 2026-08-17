# Release Process

AgentWeave is **one product with one version**. A single `v*` tag releases everything: both PyPI
distributions and the Docker image.

The `hub-v*` tag scheme used before 1.0.0 is retired. Images and releases already published under
it are untouched and keep working; nothing new is published there.

## 1. Bump the version

Two files, and they must match:

- `pyproject.toml` — `agentweave-ai`
- `hub/pyproject.toml` — `agentweave-hub`

Nothing else. `__version__` in both packages is derived from installed package metadata at import
time (`importlib.metadata.version`), so there is no literal to keep in step — an older version of
this page said to edit `src/agentweave/__init__.py`, and there has been nothing to edit there for
some time.

`agentweave-ai` depends on `agentweave-hub>=<this version>`, so the two are released together by
construction. Do not bump one alone.

## 2. Update the CHANGELOG

`CHANGELOG.md`, newest first. Anything breaking goes in its own section — the Python floor, removed
commands, changed defaults.

## 3. Merge to `master`

Open a pull request rather than pushing. `ci.yml` runs on pushes to `master` **and** on pull
requests targeting it, so a PR is what gets the full matrix — every OS, every supported Python —
to run *before* `master` moves.

**Every job must be green and finished before merging.** Publication is irreversible; a merge is
not.

## 4. Tag and release

```bash
git tag v1.2.3
git push origin v1.2.3
gh release create v1.2.3 --title "AgentWeave v1.2.3" --notes-file <notes>
```

Creating the release fires `publish.yml`, which builds and uploads **both** distributions to PyPI.
Pushing the tag fires `hub-image.yml`, which builds and pushes the Docker image to
`ghcr.io/gutohuida/agentweave-hub`, tagged with the version and with `latest`.

If only one PyPI job runs, the `if:` gates in `publish.yml` have drifted — both jobs must key off
`refs/tags/v`.

**A version number on PyPI can never be reused.** Read both `pyproject.toml` files and confirm they
say what you think before tagging.

## 5. Verify the artefact, not the workflow

A green workflow means the upload succeeded, not that the result installs:

```bash
python -m venv /tmp/verify && /tmp/verify/bin/pip install agentweave-ai==1.2.3
/tmp/verify/bin/agentweave --version
```

That also confirms `agentweave-hub` came with it, which is the point of the single-install design.

## Working with the Docker image locally

```bash
cd hub
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
```

The main compose file has no `build:` section deliberately — end users download it on its own, with
no source beside it, and Compose builds instead of pulling when a service declares both `build` and
`image`. `docker-compose.build.yml` is the contributor override that supplies one; `AW_HUB_IMAGE`
points the plain file at an image you built some other way.

`make hub-full-build` does the same thing including a UI rebuild.

## End-user deployment

Users do not need the repository:

```bash
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example
cp .env.example .env  # edit AW_BOOTSTRAP_API_KEY and AW_WORKSPACE_HOST_ROOT
docker compose up -d
```

Most users should not do this at all — `pip install agentweave-ai` then `agentweave` is the
supported path, and Docker is for remote or headless deployments.

## CI/CD

| Workflow | Fires on | Does |
|---|---|---|
| `ci.yml` | push to `master`, PRs into `master` | tests, lint, type check, build |
| `publish.yml` | a release being created on a `v*` tag | builds and uploads both distributions to PyPI |
| `hub-image.yml` | push to `master` touching `hub/**`, or a `v*` tag | builds and pushes the GHCR image |
| `docs.yml` | push to `master` | `mkdocs build --strict`, deploys to GitHub Pages |
