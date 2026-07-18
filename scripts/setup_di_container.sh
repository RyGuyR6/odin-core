#!/usr/bin/env bash
set -e

echo "==================================="
echo "Installing Odin DI Container"
echo "==================================="

mkdir -p backend/app/core

cat > backend/app/core/container.py <<'PYEOF'
class Container:
    def __init__(self):
        self._services = {}

    def register(self, cls, instance):
        self._services[cls] = instance

    def resolve(self, cls):
        if cls not in self._services:
            raise KeyError(f"{cls.__name__} is not registered")
        return self._services[cls]


container = Container()
PYEOF

echo
echo "==================================="
echo "Dependency Injection Installed"
echo "==================================="
echo
echo "Next:"
echo "Register services during Odin startup."
