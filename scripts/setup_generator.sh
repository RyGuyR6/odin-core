#!/usr/bin/env bash
set -e

echo "==================================="
echo "Installing Odin Generator"
echo "==================================="

mkdir -p backend/app/generator/templates
mkdir -p backend/app/generator

touch backend/app/generator/__init__.py

#########################################
# generator.py
#########################################

cat > backend/app/generator/generator.py <<'PYEOF'
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class Generator:

    def __init__(self):
        self.backend = ROOT / "backend"

    def service(self, name: str):
        filename = self.backend / "app" / "services" / f"{name.lower()}_service.py"

        if filename.exists():
            print(f"{filename.name} already exists.")
            return

        filename.write_text(
f'''from app.services.base import BaseService


class {name}Service(BaseService):
    name = "{name}"

'''
        )

        print(f"Created {filename}")
PYEOF

#########################################
# Update CLI
#########################################

python3 <<'PYEOF'
from pathlib import Path

path = Path("backend/app/cli/odin.py")
text = path.read_text()

if "from app.generator.generator import Generator" not in text:
    text = text.replace(
        "from pathlib import Path",
        "from pathlib import Path\nfrom app.generator.generator import Generator"
    )

if "generator = Generator()" not in text:
    text = text.replace(
        "APP = ROOT / \"backend\" / \"app\"",
        "APP = ROOT / \"backend\" / \"app\"\ngenerator = Generator()"
    )

text = text.replace(
    "create_service(args.name)",
    "generator.service(args.name)"
)

path.write_text(text)
PYEOF

echo
echo "==================================="
echo "Generator installed!"
echo "==================================="
echo
echo "Try:"
echo "./scripts/odin new service Weather"
