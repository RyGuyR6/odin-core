import argparse
from pathlib import Path

from app.cli.commands.doctor import run as doctor_command
from app.cli.commands.inspect import run as inspect_command
from app.cli.commands.validate import run as validate_command
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

    sub.add_parser(
        "doctor",
        help="Run project health checks.",
    )

    sub.add_parser(
        "inspect",
        help="Inspect the project.",
    )

    sub.add_parser(
        "validate",
        help="Run validation.",
    )

    new = sub.add_parser("new")

    new_sub = new.add_subparsers(dest="type")

    service = new_sub.add_parser("service")
    service.add_argument("name")

    args = parser.parse_args()
    args.repo_root = ROOT

    if args.command == "doctor":
        raise SystemExit(doctor_command(args))

    if args.command == "inspect":
        raise SystemExit(inspect_command(args))

    if args.command == "validate":
        raise SystemExit(validate_command(args))

    if args.command == "new":
        if args.type == "service":
            generator.service(args.name)


if __name__ == "__main__":
    main()