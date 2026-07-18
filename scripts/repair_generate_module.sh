#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cat > "$ROOT/scripts/odin_cli/generate.py" <<'PY'
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        print(f"Skipping existing {path.relative_to(BACKEND)}")
        return

    path.write_text(content)
    print(f"Created {path.relative_to(BACKEND)}")


def generate_service(name: str):
    lower = name.lower()

    _write(
        BACKEND / "app" / "services" / f"{lower}_service.py",
f'''from app.services.base import BaseService


class {name}Service(BaseService):
    name = "{name}"
'''
    )


def generate_api(name: str):
    lower = name.lower()

    _write(
        BACKEND / "app" / "api" / f"{lower}.py",
f'''from fastapi import APIRouter

router = APIRouter(
    prefix="/{lower}",
    tags=["{name}"],
)

@router.get("/")
def status():
    return {{
        "feature": "{name}",
        "status": "ok"
    }}
'''
    )


def generate_model(name: str):
    lower = name.lower()

    _write(
        BACKEND / "app" / "models" / f"{lower}.py",
f'''from sqlalchemy import Column, Integer, String
from app.database.database import Base


class {name}(Base):
    __tablename__ = "{lower}"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
'''
    )


def generate_repository(name: str):
    lower = name.lower()

    _write(
        BACKEND / "app" / "repositories" / f"{lower}_repository.py",
f'''class {name}Repository:
    pass
'''
    )


def generate_feature(name: str):
    print(f"Generating {name}...")

    generate_model(name)
    generate_repository(name)
    generate_service(name)
    generate_api(name)

    print("Done.")
PY

echo
echo "✅ generate.py repaired."
