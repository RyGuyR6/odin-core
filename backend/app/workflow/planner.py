from .models import WorkflowTask


class Planner:

    def plan(self, objective: str) -> WorkflowTask:
        return WorkflowTask(
            id="task-001",
            objective=objective,
        )
