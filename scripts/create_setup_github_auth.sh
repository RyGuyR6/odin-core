#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "Creating setup_github_auth.sh..."
echo "========================================="

mkdir -p scripts

cat > scripts/setup_github_auth.sh <<'SETUP'
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

echo "========================================="
echo "GitHub Authentication Setup"
echo "========================================="

echo
echo "This file is ready."
echo "Paste the installer contents into this file."
echo
SETUP

chmod +x scripts/setup_github_auth.sh

echo
echo "✅ Created:"
echo "   scripts/setup_github_auth.sh"
echo
echo "Next:"
echo "  Open scripts/setup_github_auth.sh"
echo "  Replace its contents with the installer I provide."
