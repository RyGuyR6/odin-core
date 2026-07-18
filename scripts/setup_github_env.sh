#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENV_FILE="$ROOT/backend/.env"

echo "======================================="
echo " Odin GitHub Environment Setup"
echo "======================================="

if [ -f "$ENV_FILE" ]; then
    echo "Existing .env found."
    read -p "Overwrite it? (y/n): " answer

    if [ "$answer" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi
fi

read -s -p "Paste your GitHub token: " TOKEN
echo

cat > "$ENV_FILE" <<EOF2
GITHUB_TOKEN=$TOKEN
EOF2

chmod 600 "$ENV_FILE"

echo
echo "GitHub token saved:"
echo "$ENV_FILE"

echo
echo "Adding .env to gitignore..."

touch "$ROOT/.gitignore"

grep -qxF "backend/.env" "$ROOT/.gitignore" || \
echo "backend/.env" >> "$ROOT/.gitignore"

echo
echo "======================================="
echo " GitHub environment ready"
echo "======================================="
