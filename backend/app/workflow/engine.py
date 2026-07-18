from .executor import Executor
from .planner import Planner
from .reviewer import Reviewer


class WorkflowEngine:

    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()
        self.reviewer = Reviewer()

    def run(self, objective: str):
        task = self.planner.plan(objective)
        result = self.executor.execute(task)
        return self.reviewer.review(result)
