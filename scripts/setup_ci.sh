#!/usr/bin/env bash
set -e

echo "==================================="
echo "Installing CI"
echo "==================================="

mkdir -p .github/workflows
mkdir -p backend/tests/services

#########################################
# Sample service test
#########################################

cat > backend/tests/services/test_health_service.py <<'PYEOF'
from app.services.health_service import HealthService


def test_health_service():
    service = HealthService()

    result = service.get_status()

    assert result["status"] == "healthy"
PYEOF

#########################################
# GitHub Actions workflow
#########################################

cat > .github/workflows/backend.yml <<'YAMLEOF'
name: Backend CI

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest

    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run tests
        run: pytest
YAMLEOF

echo
echo "==================================="
echo "CI Installed"
echo "==================================="
echo
echo "Run locally:"
echo "make test"
