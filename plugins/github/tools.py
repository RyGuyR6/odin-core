from app.sdk import Tool


def list_repositories():
    """
    Placeholder GitHub repository listing.
    API integration comes next.
    """

    return {
        "repositories": []
    }


def read_file(path: str):
    return {
        "file": path,
        "content": None,
        "message": "GitHub API connection pending"
    }


def search(query: str):
    return {
        "query": query,
        "results": []
    }


github_tools = [
    Tool(
        name="github.list_repositories",
        description="List GitHub repositories",
        handler=list_repositories,
    ),

    Tool(
        name="github.read_file",
        description="Read a file from GitHub",
        handler=read_file,
    ),

    Tool(
        name="github.search",
        description="Search GitHub code",
        handler=search,
    ),
]
