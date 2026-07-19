import importlib
import inspect
import pkgutil

import app.workflows as workflows_package

from app.workflows.registry import registry


_loaded = False


def load_workflows():

    global _loaded

    if _loaded:
        return

    for module in pkgutil.iter_modules(workflows_package.__path__):

        if not module.name.endswith("_workflow"):
            continue

        imported = importlib.import_module(
            f"app.workflows.{module.name}"
        )

        for _, cls in inspect.getmembers(imported, inspect.isclass):

            if cls.__module__ != imported.__name__:
                continue

            registry.register(cls.__name__, cls())

    _loaded = True
