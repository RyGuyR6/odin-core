#!/usr/bin/env bash

set +e

echo
echo "========== Ruff =========="
ruff check backend

echo
echo "========== MyPy =========="
mypy backend/app

echo
echo "========== Pytest =========="
cd backend
pytest -v tests/repository