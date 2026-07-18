
class WorkflowRegistry:
    """
    Stores all available workflows.
    """

    def __init__(self):
        self._workflows = {}

    def register(self, name: str, workflow):
        self._workflows[name] = workflow

    def get(self, name: str):
        if name not in self._workflows:
            raise KeyError(f"Workflow '{name}' is not registered.")

        return self._workflows[name]

    def list(self):
        return sorted(self._workflows.keys())
