from functools import wraps
from inspect import signature
from typing import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.tools.loader import load_tools
from app.tools.registry import registry


def create_mcp_handler(tool) -> Callable:
    execute = tool.execute

    @wraps(execute)
    def handler(**kwargs):
        return execute(**kwargs)

    handler.__name__ = tool.name.replace("-", "_")
    handler.__doc__ = tool.description
    handler.__signature__ = signature(execute)
    return handler


def create_mcp() -> FastMCP:
    """Create a fresh MCP server with a fresh single-use session manager."""
    server = FastMCP(
        name="Odin",
        instructions=(
            "Odin is a controlled engineering execution service. "
            "Use its tools to inspect and modify repositories through "
            "Odin-managed credentials and workflows."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "odin-api-63t2.onrender.com",
                "odin-api-63t2.onrender.com:*",
                "api.odincore.net",
                "api.odincore.net:*",
                "localhost",
                "localhost:*",
                "127.0.0.1",
                "127.0.0.1:*",
            ],
        ),
    )

    load_tools()
    for tool in registry.all():
        handler = create_mcp_handler(tool)
        server.tool(
            name=tool.name,
            description=tool.description,
        )(handler)

    return server


# Compatibility instance for callers that import app.mcp_server.mcp.
# FastAPI lifespan execution creates a new instance via create_mcp().
mcp = create_mcp()
