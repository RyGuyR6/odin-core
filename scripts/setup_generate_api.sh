#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing Generate API Command"
echo "========================================"

#########################################
# Update generate.py
#########################################

cat >> "$ROOT/scripts/odin_cli/generate.py" <<'PY'

def generate_api(name: str):
    api_dir = BACKEND / "app" / "api"
    api_dir.mkdir(parents=True, exist_ok=True)

    filename = api_dir / f"{name.lower()}.py"

    if filename.exists():
        print(f"{filename.name} already exists.")
        return

    filename.write_text(
f'''from fastapi import APIRouter

router = APIRouter(
    prefix="/{name.lower()}",
    tags=["{name}"],
)


@router.get("/")
def get_{name.lower()}():
    return {{
        "service": "{name}",
        "status": "ok"
    }}
'''
    )

    print(f"Created {filename.relative_to(BACKEND)}")
PY

#########################################
# Update CLI
#########################################

python3 <<'PY'
from pathlib import Path

path = Path("scripts/odin.py")
text = path.read_text()

old = """generate_sub = generate_cmd.add_subparsers(dest="type")"""

if old not in text:
    raise SystemExit("Could not find generate parser.")

replacement = old

text = text.replace(old, replacement)

api_block = '''

api_cmd = generate_sub.add_parser("api")
api_cmd.add_argument("name")
api_cmd.set_defaults(
    func=lambda args: generate.generate_api(args.name)
)
'''

if "generate_api" not in text:
    marker = 'service_cmd.set_defaults(\n    func=lambda args: generate.generate_service(args.name)\n)\n'
    text = text.replace(marker, marker + api_block)

path.write_text(text)
PY

echo
echo "========================================"
echo "Generate API Installed"
echo "========================================"

echo
echo "Try:"
echo "python scripts/odin.py generate api Weather"
