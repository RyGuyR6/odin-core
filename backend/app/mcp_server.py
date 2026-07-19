from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.workflows.github.modify_file import ModifyFileWorkflow


mcp = FastMCP(
    name="Odin",
    instructions=(
        "Odin is a controlled engineering execution service. "
        "Use its tools to inspect and modify GitHub repositories "
        "through Odin-managed credentials."
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


@mcp.tool()
def odin_health() -> dict[str, str]:
    """Check whether the Odin MCP server is operational."""
    return {
        "status": "healthy",
        "service": "odin",
        "transport": "mcp-streamable-http",
    }


@mcp.tool()
def github_modify_file_and_open_pr(
    owner: str,
    repo: str,
    path: str,
    content: str,
    commit_message: str,
    pr_title: str,
    pr_body: str = "",
) -> dict:
    """Replace one GitHub file on a new branch and open a pull request.

    Odin performs the GitHub write using its server-side credentials.
    This tool does not write directly to the default branch.
    """
    workflow = ModifyFileWorkflow()

    return workflow.run(
        owner=owner,
        repo=repo,
        path=path,
        content=content,
        commit_message=commit_message,
        pr_title=pr_title,
        pr_body=pr_body,
    )
