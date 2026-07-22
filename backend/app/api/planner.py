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
        "repository_package": plan.metadata.get("repository_package"),
        "repository_summary": plan.metadata.get("repository_summary"),
        "candidate_files": plan.metadata.get("candidate_files", []),
        "affected_symbols": plan.metadata.get("affected_symbols", []),
        "dependencies": plan.metadata.get("dependencies", []),
        "likely_tests": plan.metadata.get("likely_tests", []),
        "notes": plan.metadata.get("notes", []),
        "memory_context": plan.metadata.get("memory_context", []),
        "result": result.to_dict(),
    }


@router.post("/ai")
async def execute_goal_ai(payload: dict):
    """AI-powered planning endpoint.

    The planner calls the centralized LLM platform to generate a structured
    execution plan.  It never calls OpenAI directly.
    """
    goal = payload["goal"]
    repository = payload.get("repository")
    profile = payload.get("profile")
    plan = await planner.create_ai_plan(goal, repository=repository, profile=profile)
    result = plan_executor.execute(plan)

    return {
        "goal": goal,
        "steps": len(plan.steps),
        "ai_generated": plan.metadata.get("ai_generated", False),
        "ai_model": plan.metadata.get("ai_model"),
        "phases": plan.metadata.get("phases", []),
        "repository": plan.metadata.get("repository"),
        "candidate_files": plan.metadata.get("candidate_files", []),
        "notes": plan.metadata.get("notes", []),
        "memory_context": plan.metadata.get("memory_context", []),
        "result": result.to_dict(),
    }
