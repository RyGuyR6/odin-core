from pathlib import Path

from odin_mcp.core.brain import OdinBrain
from odin_mcp.core.brain_pipeline import BrainPipeline

from odin_mcp.services.repository_planner import RepositoryPlanner
from odin_mcp.services.repository_search_service import RepositorySearchService
from odin_mcp.services.engineering_planner import EngineeringPlanner

brain = OdinBrain()

repo = RepositorySearchService(Path("."))

brain.register(
    "repository_planner",
    RepositoryPlanner(repo),
)

brain.register(
    "engineering_planner",
    EngineeringPlanner(),
)

brain.register(
    "executor",
    None,
)

pipeline = BrainPipeline(brain)

ctx = brain.create_context(
    "Add JWT authentication"
)

ctx = pipeline.run(ctx)

print()

print("Goal")
print("-----")
print(ctx.goal)

print()

print("Decision Graph")
print("--------------")
print(ctx.decision_graph)

print()

print("Repository Analysis")
print("-------------------")
print(ctx.repository_analysis)

print()

print("Engineering Plan")
print("----------------")
print(ctx.engineering_plan)
