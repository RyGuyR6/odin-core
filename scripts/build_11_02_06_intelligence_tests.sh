#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

TEST_DIR="backend/tests/intelligence"
mkdir -p "$TEST_DIR"

###############################################################################
# test_models.py
###############################################################################

cat > "$TEST_DIR/test_models.py" <<'PY'
from app.intelligence.models import ModuleInfo, PackageInfo, ProjectInventory


def test_inventory_defaults():
    inventory = ProjectInventory()

    assert inventory.packages == []
    assert inventory.module_count == 0


def test_package_module_relationship():
    package = PackageInfo(name="core")
    package.modules.append(ModuleInfo(name="repo", path="repo.py"))

    assert len(package.modules) == 1
    assert package.modules[0].name == "repo"
PY

###############################################################################
# test_queries.py
###############################################################################

cat > "$TEST_DIR/test_queries.py" <<'PY'
from app.intelligence.models import (
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)

from app.intelligence.queries import IntelligenceQueryEngine


def build_inventory():
    inventory = ProjectInventory()

    pkg = PackageInfo(name="repository")
    pkg.modules.append(ModuleInfo(name="loader", path="loader.py"))

    inventory.packages.append(pkg)

    return inventory


def test_find_module():
    query = IntelligenceQueryEngine(build_inventory())

    module = query.find_module("loader")

    assert module is not None
    assert module.name == "loader"


def test_statistics():
    stats = IntelligenceQueryEngine(build_inventory()).statistics()

    assert stats["packages"] == 1
    assert stats["modules"] == 1
PY

###############################################################################
# Verify creation
###############################################################################

echo
echo "Created test files:"
find "$TEST_DIR" -type f | sort

[[ -f "$TEST_DIR/test_models.py" ]]
[[ -f "$TEST_DIR/test_queries.py" ]]

echo
echo "Intelligence test suite created successfully."