from fastapi import APIRouter

from app.planning.executor import plan_executor
from app.planning.planner import planner

router = APIRouter(
    prefix="/planner",
    tags=["Planner"],
)


@router.post("/")
def execute_goal(payload: dict):
    goal = payload["goal"]
    repository = payload.get("repository")
    plan = planner.create_plan(goal, repository=repository)
    result = plan_executor.execute(plan)

    return {
        "goal": goal,
        "steps": len(plan.steps),
        "phases": plan.metadata.get("phases", []),
        "repository": plan.metadata.get("repository"),
        "repository_context": plan.metadata.get("repository_context"),
        "repository_summary": plan.metadata.get("repository_summary"),
        "candidate_files": plan.metadata.get("candidate_files", []),
        "notes": plan.metadata.get("notes", []),
        "result": result.to_dict(),
    }
