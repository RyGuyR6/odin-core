#!/usr/bin/env bash
set -e

echo "========================================"
echo "Installing Odin Plugin System"
echo "========================================"

mkdir -p backend/app/plugins

#########################################
# plugin base
#########################################

cat > backend/app/plugins/base.py <<'PYEOF'
from abc import ABC, abstractmethod


class BasePlugin(ABC):
    name = "Unknown"

    @abstractmethod
    def register(self, container):
        pass
PYEOF

#########################################
# plugin loader
#########################################

cat > backend/app/plugins/loader.py <<'PYEOF'
import importlib
import pkgutil

from app.plugins.base import BasePlugin


class PluginLoader:

    def __init__(self):
        self.plugins = []

    def load(self):
        import app.plugins

        for _, module_name, _ in pkgutil.iter_modules(app.plugins.__path__):
            if module_name in ("base", "loader"):
                continue

            module = importlib.import_module(f"app.plugins.{module_name}")

            for obj in module.__dict__.values():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BasePlugin)
                    and obj is not BasePlugin
                ):
                    self.plugins.append(obj())

    def register(self, container):
        for plugin in self.plugins:
            plugin.register(container)
PYEOF

#########################################
# health plugin
#########################################

cat > backend/app/plugins/health.py <<'PYEOF'
from app.plugins.base import BasePlugin
from app.services.health_service import HealthService


class HealthPlugin(BasePlugin):
    name = "Health"

    def register(self, container):
        container.register("health", HealthService())
PYEOF

#########################################
# github plugin
#########################################

cat > backend/app/plugins/github.py <<'PYEOF'
from app.plugins.base import BasePlugin
from app.services.github_service import GitHubService


class GitHubPlugin(BasePlugin):
    name = "GitHub"

    def register(self, container):
        container.register("github", GitHubService())
PYEOF

touch backend/app/plugins/__init__.py

echo
echo "========================================"
echo "Plugin system installed."
echo "========================================"
echo
echo "Next:"
echo "Update Odin to use PluginLoader."
