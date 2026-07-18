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
