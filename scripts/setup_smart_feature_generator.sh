#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing Smart Feature Generator"
echo "========================================"

python3 <<'PY'
from pathlib import Path

path = Path("scripts/odin_cli/generate.py")
text = path.read_text()

start = text.find("def generate_feature(")
if start == -1:
    raise SystemExit("generate_feature() not found.")

end = text.find("\ndef ", start + 1)
if end == -1:
    end = len(text)

new_function = '''
def generate_feature(name: str):
    print(f"Generating feature: {name}")

    generators = [
        ("Model", generate_model),
        ("Repository", generate_repository),
        ("Service", generate_service),
    ]

    optional = [
        ("Schema", globals().get("generate_schema")),
        ("API", globals().get("generate_api")),
        ("Plugin", globals().get("generate_plugin")),
        ("Test", globals().get("generate_test")),
    ]

    generators.extend([(n, f) for n, f in optional if callable(f)])

    for label, func in generators:
        print(f" -> {label}")
        func(name)

    print(f"✓ Feature {name} generated.")
'''

updated = text[:start] + new_function + text[end:]
path.write_text(updated)

print("Updated generate_feature().")
PY

echo
echo "========================================"
echo "Smart Feature Generator Installed"
echo "========================================"
