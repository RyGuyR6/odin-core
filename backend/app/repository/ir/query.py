from __future__ import annotations


class IRQuery:
    """
    High-level query interface for the Odin Intermediate Representation.
    """

    def __init__(self, modules):
        self._modules = modules

    def modules(self):
        return list(self._modules)

    def classes(self):
        return [
            cls
            for module in self._modules
            for cls in module.classes
        ]

    def functions(self):
        functions = []

        for module in self._modules:
            functions.extend(module.functions)

            for cls in module.classes:
                functions.extend(cls.methods)

        return functions

    def find_class(self, qualified_name: str):
        for cls in self.classes():
            if cls.qualified_name == qualified_name:
                return cls
        return None

    def find_function(self, qualified_name: str):
        for fn in self.functions():
            if fn.qualified_name == qualified_name:
                return fn
        return None
