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
