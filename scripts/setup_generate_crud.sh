#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing CRUD Generator"
echo "========================================"

mkdir -p "$ROOT/backend/app/schemas"

#########################################
# Extend generate.py
#########################################

cat >> "$ROOT/scripts/odin_cli/generate.py" <<'PY'

def generate_crud(name: str):
    lower = name.lower()

    generate_feature(name)

    schema = BACKEND / "app/schemas" / f"{lower}.py"

    if not schema.exists():
        schema.write_text(
f'''from pydantic import BaseModel


class {name}Create(BaseModel):
    name: str


class {name}Response({name}Create):
    id: int
'''
        )

        print(f"Created {schema.relative_to(BACKEND)}")
PY

#########################################
# Patch CLI
#########################################

python3 <<'PY'
from pathlib import Path

path = Path("scripts/odin.py")
text = path.read_text()

block = '''

crud_cmd = generate_sub.add_parser("crud")
crud_cmd.add_argument("name")
crud_cmd.set_defaults(
    func=lambda args: generate.generate_crud(args.name)
)
'''

if "generate_crud" not in text:
    marker = '''
feature_cmd.set_defaults(
    func=lambda args: generate.generate_feature(args.name)
)
'''
    text = text.replace(marker, marker + block)

path.write_text(text)
PY

echo
echo "========================================"
echo "CRUD Generator Installed"
echo "========================================"
echo
echo "Run:"
echo "python scripts/odin.py generate crud Product"
