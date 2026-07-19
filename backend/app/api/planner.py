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

    plan = planner.create_plan(goal)

    return {
        "goal": goal,
        "steps": len(plan.steps),
        "result": plan_executor.execute(plan),
    }
