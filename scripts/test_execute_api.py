from pathlib import Path

from odin_mcp.core.execute import OdinExecuteAPI

api = OdinExecuteAPI(
    Path(".")
)

response = api.execute(
    "Add JWT authentication"
)

print()

print(response)

print()

print(response.context.decision_graph)
