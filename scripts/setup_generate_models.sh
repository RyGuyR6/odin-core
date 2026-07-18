#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing SQLAlchemy Model Generator"
echo "========================================"

cat >> "$ROOT/scripts/odin_cli/generate.py" <<'PY'

def generate_model(name: str):
    lower = name.lower()

    models = BACKEND / "app/models"
    models.mkdir(parents=True, exist_ok=True)

    filename = models / f"{lower}.py"

    if filename.exists():
        print(f"{filename.name} already exists.")
        return

    filename.write_text(
f'''from sqlalchemy import Column, Integer, String
from app.database.database import Base


class {name}(Base):
    __tablename__ = "{lower}"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
''')

    print(f"Created {filename.relative_to(BACKEND)}")
PY

python3 <<'PY'
from pathlib import Path

path = Path("scripts/odin.py")
text = path.read_text()

if "model_cmd" not in text:
    marker = '''
crud_cmd.set_defaults(
    func=lambda args: generate.generate_crud(args.name)
)
'''

    addition = '''

model_cmd = generate_sub.add_parser("model")
model_cmd.add_argument("name")
model_cmd.set_defaults(
    func=lambda args: generate.generate_model(args.name)
)
'''

    text = text.replace(marker, marker + addition)

path.write_text(text)
PY

echo
echo "Installed SQLAlchemy model generator."
