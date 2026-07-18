from app.sdk import Plugin

from .tools import github_tools


class GitHubPlugin(Plugin):

    name = "github"
    version = "0.1.0"


    def load(self, context):
        self.context = context


    def tools(self):
        return github_tools
