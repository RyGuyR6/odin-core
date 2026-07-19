from functools import wraps
from inspect import signature
from typing import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.tools.loader import load_tools
from app.tools.registry import registry


mcp = FastMCP(
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
            "odin-core.onrender.com",
            "odin-core.onrender.com:*",
            "api.odincore.net",
            "api.odincore.net:*",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ],
    ),
)


def create_mcp_handler(tool) -> Callable:
    """
    Create a standalone function that delegates execution to an Odin tool.

    A standalone wrapper is necessary because attributes such as __name__
    and __signature__ cannot safely be assigned to a bound method.
    """
    execute = tool.execute

    @wraps(execute)
    def handler(**kwargs):
        return execute(**kwargs)

    handler.__name__ = tool.name.replace("-", "_")
    handler.__doc__ = tool.description
    handler.__signature__ = signature(execute)

    return handler


def register_registry_tools() -> None:
    load_tools()

    for tool in registry.all():
        handler = create_mcp_handler(tool)

        mcp.tool(
            name=tool.name,
            description=tool.description,
        )(handler)


register_registry_tools()
