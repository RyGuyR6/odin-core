from pathlib import Path

from odin_mcp.core.orchestrator import Odin

odin = Odin(
    Path(".")
)

result = odin.execute(
    "Add JWT authentication"
)

print(result)
