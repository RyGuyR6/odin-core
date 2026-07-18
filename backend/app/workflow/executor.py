from .models import WorkflowResult, WorkflowTask


class Executor:

    def execute(self, task: WorkflowTask) -> WorkflowResult:
        return WorkflowResult(
            success=True,
            message=f"Executed: {task.objective}",
        )
