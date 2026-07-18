from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class FeatureGenerator:
    def __init__(self):
        self.backend = ROOT / "backend"

    def _write(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            print(f"Skipping existing {path.name}")
            return

        path.write_text(content)
        print(f"Created {path.relative_to(self.backend)}")

    def generate(self, name: str):
        lower = name.lower()

        self._write(
            self.backend / "app" / "services" / f"{lower}_service.py",
f'''from app.services.base import BaseService


class {name}Service(BaseService):
    name = "{name}"
'''
        )

        self._write(
            self.backend / "app" / "api" / f"{lower}.py",
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

        self._write(
            self.backend / "app" / "plugins" / f"{lower}.py",
f'''from app.plugins.base import BasePlugin


class {name}Plugin(BasePlugin):
    name = "{name}"

    def register(self, container):
        pass
'''
        )

        self._write(
            self.backend / "tests" / f"test_{lower}.py",
f'''def test_{lower}_placeholder():
    assert True
'''
        )
