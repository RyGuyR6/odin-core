#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing Generate Service Command"
echo "========================================"

#########################################
# generate.py
#########################################

cat > "$ROOT/scripts/odin_cli/generate.py" <<'PY'
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def generate_service(name: str):
    services = BACKEND / "app" / "services"
    services.mkdir(parents=True, exist_ok=True)

    filename = services / f"{name.lower()}_service.py"

    if filename.exists():
        print(f"{filename.name} already exists.")
        return

    filename.write_text(
f'''from app.services.base import BaseService


class {name}Service(BaseService):
    name = "{name}"

    def __init__(self):
        super().__init__()
'''
    )

    print(f"Created {filename.relative_to(BACKEND)}")
PY

#########################################
# Update odin.py
#########################################

cat > "$ROOT/scripts/odin.py" <<'PY'
#!/usr/bin/env python3

import argparse

from odin_cli import doctor
from odin_cli import generate

parser = argparse.ArgumentParser(prog="odin")

sub = parser.add_subparsers(dest="command")

doctor_cmd = sub.add_parser("doctor")
doctor_cmd.set_defaults(func=lambda args: doctor.run())

generate_cmd = sub.add_parser("generate")
generate_sub = generate_cmd.add_subparsers(dest="type")

service_cmd = generate_sub.add_parser("service")
service_cmd.add_argument("name")
service_cmd.set_defaults(
    func=lambda args: generate.generate_service(args.name)
)

args = parser.parse_args()

if hasattr(args, "func"):
    args.func(args)
else:
    parser.print_help()
PY

chmod +x "$ROOT/scripts/odin.py"

echo
echo "========================================"
echo "Generate command installed."
echo "========================================"
echo
echo "Try:"
echo "python scripts/odin.py generate service Weather"
