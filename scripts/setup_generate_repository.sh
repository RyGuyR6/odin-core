#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing Repository Generator"
echo "========================================"

mkdir -p "$ROOT/backend/app/repositories"

#########################################
# Extend generate.py
#########################################

cat >> "$ROOT/scripts/odin_cli/generate.py" <<'PY'

def generate_repository(name: str):
    lower = name.lower()

    repo_dir = BACKEND / "app" / "repositories"
    repo_dir.mkdir(parents=True, exist_ok=True)

    filename = repo_dir / f"{lower}_repository.py"

    if filename.exists():
        print(f"{filename.name} already exists.")
        return

    filename.write_text(
f'''from sqlalchemy.orm import Session

from app.models.{lower} import {name}


class {name}Repository:

    def __init__(self, db: Session):
        self.db = db

    def get(self, entity_id: int):
        return self.db.get({name}, entity_id)

    def list(self):
        return self.db.query({name}).all()

    def create(self, entity: {name}):
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity_id: int):
        entity = self.get(entity_id)
        if entity is None:
            return False

        self.db.delete(entity)
        self.db.commit()
        return True
''')

    print(f"Created {filename.relative_to(BACKEND)}")
PY

#########################################
# Patch CLI
#########################################

python3 <<'PY'
from pathlib import Path

path = Path("scripts/odin.py")
text = path.read_text()

if "repository_cmd" not in text:
    marker = '''
model_cmd.set_defaults(
    func=lambda args: generate.generate_model(args.name)
)
'''

    addition = '''

repository_cmd = generate_sub.add_parser("repository")
repository_cmd.add_argument("name")
repository_cmd.set_defaults(
    func=lambda args: generate.generate_repository(args.name)
)
'''

    if marker in text:
        text = text.replace(marker, marker + addition)
        path.write_text(text)
    else:
        print("WARNING: Could not automatically patch scripts/odin.py")
PY

echo
echo "========================================"
echo "Repository Generator Installed"
echo "========================================"

echo
echo "Try:"
echo "python scripts/odin.py generate repository Customer"
