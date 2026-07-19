from app.workflows.loader import load_workflows
from app.workflows.registry import registry


class WorkflowService:
    """
    Resolve and execute registered Odin workflows.
    """

    def __init__(self):
        load_workflows()

    def execute(self, workflow_name: str, **kwargs):
        workflow = registry.get(workflow_name)
        return workflow.run(**kwargs)

    def list(self) -> list[str]:
        return registry.list()
