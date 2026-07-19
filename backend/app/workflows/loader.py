import importlib
import inspect
import pkgutil

import app.workflows as workflows_package
from app.workflows.registry import registry


_loaded = False


def load_workflows() -> None:
    """
    Recursively discover and register workflow classes under app.workflows.
    """
    global _loaded

    if _loaded:
        return

    prefix = f"{workflows_package.__name__}."

    for module_info in pkgutil.walk_packages(
        workflows_package.__path__,
        prefix=prefix,
    ):
        module_name = module_info.name

        if module_name.endswith(".registry"):
            continue

        if module_name.endswith(".loader"):
            continue

        module = importlib.import_module(module_name)

        for _, workflow_class in inspect.getmembers(
            module,
            inspect.isclass,
        ):
            if workflow_class.__module__ != module.__name__:
                continue

            if not workflow_class.__name__.endswith("Workflow"):
                continue

            if not callable(getattr(workflow_class, "run", None)):
                continue

            registry.register(
                workflow_class.__name__,
                workflow_class(),
            )

    _loaded = True
