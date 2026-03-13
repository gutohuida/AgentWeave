#!/usr/bin/env bash
set -e

echo "Building AgentWeave Hub image from source..."
docker build https://github.com/gutohuida/AgentWeave.git#master:hub -t agentweave-hub:latest

if [ ! -f .env ]; then
  echo ""
  echo "No .env file found. Creating from .env.example..."
  curl -fsSO https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example
  cp .env.example .env
  echo ""
  echo "IMPORTANT: Edit .env and set AW_BOOTSTRAP_API_KEY before continuing."
  echo "  Generate a key: python3 -c \"import secrets; print('aw_live_' + secrets.token_hex(16))\""
  exit 1
fi

echo ""
echo "Starting Hub..."
docker compose up -d

echo ""
echo "Hub is running at http://localhost:8000"
echo "Open the dashboard and enter your API key from .env to connect."
