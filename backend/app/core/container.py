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
