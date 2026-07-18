import importlib
from pathlib import Path

from app.sdk.context import Context
from app.registry import registry


class PluginLoader:
    """
    Discovers and loads Odin plugins.
    """

    def __init__(self, directory="plugins"):
        self.directory = Path(directory)
        self.loaded = []


    def discover(self):
        if not self.directory.exists():
            return []

        return [
            p
            for p in self.directory.iterdir()
            if p.is_dir()
            and (p / "plugin.py").exists()
        ]


    def load_all(self):

        context = Context()

        for plugin_path in self.discover():

            module_name = (
                f"{plugin_path.name}.plugin"
            )

            module = importlib.import_module(
                module_name
            )

            plugin_class = None

            for item in dir(module):
                obj = getattr(
                    module,
                    item
                )

                if (
                    isinstance(obj, type)
                    and obj.__name__.endswith("Plugin")
                ):
                    plugin_class = obj
                    break


            if plugin_class:

                plugin = plugin_class()

                plugin.load(context)

                for tool in plugin.tools():
                    registry.register(tool)

                self.loaded.append(
                    plugin.name
                )


        return self.loaded
