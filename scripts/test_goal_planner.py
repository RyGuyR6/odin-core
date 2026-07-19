from odin_mcp.models.engineering_goal import EngineeringGoal
from odin_mcp.services.goal_planner import GoalPlanner

planner = GoalPlanner()

goal = EngineeringGoal(
    request="Add JWT authentication",
    validate=True,
    commit=True,
    push=False,
)

breakdown = planner.create_breakdown(goal)

print("Goal:")
print(goal)
print()
print("Execution Phases:")

for i, phase in enumerate(breakdown.phases, start=1):
    print(f"{i}. {phase}")
