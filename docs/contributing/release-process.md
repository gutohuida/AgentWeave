# Release Process

This guide covers how to release new versions of the CLI and Hub.

## CLI Release (PyPI)

### Version Bumping

Update both:

- `pyproject.toml` `[project]` section
- `src/agentweave/__init__.py` (`__version__`)

### Build and Upload

```bash
python -m build
python -m twine upload dist/*
```

### GitHub Release

Create a GitHub release with the new version tag. The CI workflow (`publish.yml`) can also automate this.

## Hub Release (Docker)

### Build Image

```bash
cd hub
docker compose up --build -d
```

### Full Rebuild

```bash
make hub-full-build
```

## End-User Hub Deployment

Users can deploy the Hub without cloning the full repo:

```bash
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example
cp .env.example .env  # edit AW_BOOTSTRAP_API_KEY
docker compose up -d
```

## CI/CD

The repository uses GitHub Actions:

- `ci.yml` — tests, lint, type check, and build verification
- `publish.yml` — PyPI publication on release
- `hub-image.yml` — Docker image build and push
