from odin_mcp.services.engineering_planner import EngineeringPlanner

planner = EngineeringPlanner()

plan = planner.create_replace_plan(
    title="Replace demo",
    path="odin_mcp_write_test.txt",
    old="old",
    new="new",
    commit_message="planner test",
)

print(plan)
print(f"Steps: {plan.step_count}")
for i, step in enumerate(plan.steps, start=1):
    print(f"{i}. {step.action} -> {step.parameters}")
