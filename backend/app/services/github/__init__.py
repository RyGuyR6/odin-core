"""
GitHub service package.

Expose a single shared GitHubProvider instance for the application.
Business logic (GitHubOperations) should be instantiated by workflows
or injected by the Kernel, not shared globally.
"""

from .provider import GitHubProvider

github = GitHubProvider()
