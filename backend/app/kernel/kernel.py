
from app.kernel.registry import WorkflowRegistry
from app.workflows.github import ModifyFileWorkflow


class Kernel:

    def __init__(self):
        self.registry = WorkflowRegistry()

        self.registry.register(
            "github.modify_file",
            ModifyFileWorkflow(),
        )

    def run(self, workflow_name: str, **kwargs):
        workflow = self.registry.get(workflow_name)
        return workflow.run(**kwargs)


kernel = Kernel()
