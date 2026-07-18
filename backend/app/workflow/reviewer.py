from .models import WorkflowResult


class Reviewer:

    def review(self, result: WorkflowResult) -> WorkflowResult:
        return result
