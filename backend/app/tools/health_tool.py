from app.tools.base import BaseTool


class HealthTool(BaseTool):
    name = "health"
    description = "Returns Odin health status."

    def execute(self):
        return {"status": "healthy"}
