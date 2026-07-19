from app.core.executor import executor


class PlanExecutor:

    def execute(self, plan):

        results = []

        for step in plan.steps:

            results.append(
                executor.execute(
                    step.tool,
                    **step.parameters,
                )
            )

        return results


plan_executor = PlanExecutor()
