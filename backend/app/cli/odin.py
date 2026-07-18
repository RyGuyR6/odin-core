import argparse
from pathlib import Path
from app.generator.generator import Generator


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "backend" / "app"
generator = Generator()


def create_service(name: str):
    class_name = f"{name}Service"
    filename = APP / "services" / f"{name.lower()}_service.py"

    if filename.exists():
        print(f"{filename.name} already exists.")
        return

    filename.write_text(
f'''from app.services.base import BaseService


class {class_name}(BaseService):
    name = "{name}"

'''
    )

    print(f"Created {filename}")


def main():
    parser = argparse.ArgumentParser(prog="odin")

    sub = parser.add_subparsers(dest="command")

    new = sub.add_parser("new")

    new_sub = new.add_subparsers(dest="type")

    service = new_sub.add_parser("service")
    service.add_argument("name")

    args = parser.parse_args()

    if args.command == "new":
        if args.type == "service":
            generator.service(args.name)


if __name__ == "__main__":
    main()
