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
