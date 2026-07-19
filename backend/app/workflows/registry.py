class WorkflowRegistry:
    """
    Registry for Odin workflows.
    """

    def __init__(self):
        self._workflows = {}

    def register(self, name, workflow):
        self._workflows[name] = workflow

    def get(self, name):
        return self._workflows[name]

    def list(self):
        return sorted(self._workflows.keys())

    def all(self):
        return self._workflows


registry = WorkflowRegistry()
