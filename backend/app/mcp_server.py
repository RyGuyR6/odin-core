from inspect import signature

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.tools.registry import registry


mcp = FastMCP(
    name="Odin",
    instructions=(
        "Odin is a controlled engineering execution service."
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


def register_registry_tools():

    for tool in registry.all():

        execute = tool.execute

        wrapper = execute

        wrapper.__name__ = tool.name.replace("-", "_")
        wrapper.__doc__ = tool.description
        wrapper.__signature__ = signature(execute)

        mcp.tool(
            name=tool.name,
            description=tool.description,
        )(wrapper)


register_registry_tools()
