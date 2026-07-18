#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing Feature Generator"
echo "========================================"

#########################################
# Update generate.py
#########################################

cat >> "$ROOT/scripts/odin_cli/generate.py" <<'PY'

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        print(f"Skipping {path.name}")
        return

    path.write_text(text)
    print(f"Created {path.relative_to(BACKEND)}")


def generate_feature(name: str):
    lower = name.lower()

    _write(
        BACKEND / "app/services" / f"{lower}_service.py",
f'''from app.services.base import BaseService


class {name}Service(BaseService):
    name = "{name}"
'''
    )

    _write(
        BACKEND / "app/api" / f"{lower}.py",
f'''from fastapi import APIRouter

router = APIRouter(
    prefix="/{lower}",
    tags=["{name}"],
)

@router.get("/")
def status():
    return {{
        "feature":"{name}",
        "status":"ok"
    }}
'''
    )

    _write(
        BACKEND / "app/repositories" / f"{lower}_repository.py",
f'''class {name}Repository:
    pass
'''
    )

    _write(
        BACKEND / "app/models" / f"{lower}.py",
f'''class {name}:
    pass
'''
    )

    _write(
        BACKEND / "app/plugins" / f"{lower}.py",
f'''from app.plugins.base import BasePlugin


class {name}Plugin(BasePlugin):

    name = "{name}"

    def register(self, container):
        pass
'''
    )

    _write(
        BACKEND / "tests" / f"test_{lower}.py",
f'''def test_{lower}():
    assert True
'''
    )
PY

#########################################
# Patch CLI
#########################################

python3 <<'PY'
from pathlib import Path

path = Path("scripts/odin.py")
text = path.read_text()

block = '''

feature_cmd = generate_sub.add_parser("feature")
feature_cmd.add_argument("name")
feature_cmd.set_defaults(
    func=lambda args: generate.generate_feature(args.name)
)
'''

if "generate_feature" not in text:
    marker = '''
api_cmd.set_defaults(
    func=lambda args: generate.generate_api(args.name)
)
'''
    text = text.replace(marker, marker + block)

path.write_text(text)
PY

echo
echo "========================================"
echo "Feature Generator Installed"
echo "========================================"
echo
echo "Run:"
echo "python scripts/odin.py generate feature Inventory"

