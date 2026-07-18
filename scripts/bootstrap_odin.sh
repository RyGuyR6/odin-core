#!/usr/bin/env bash
set -e

echo "========================================"
echo "🚀 Bootstrapping Odin"
echo "========================================"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"

if [ ! -d "$BACKEND" ]; then
    echo "❌ backend directory not found."
    exit 1
fi

cd "$BACKEND"

echo "Creating package structure..."
mkdir -p app/{ai,api,cli,core,database,generator,memory,models,plugins,repositories,services,tools,utils}

find app -type d -exec touch {}/__init__.py \;

mkdir -p data logs

if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found."
    exit 1
fi

echo "Python:"
.venv/bin/python --version

echo "Bootstrap complete."
