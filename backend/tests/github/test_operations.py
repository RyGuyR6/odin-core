from unittest.mock import MagicMock

from app.services.github.operations import GitHubOperations


def test_create_feature_branch():

    operations = GitHubOperations()

    operations.github = MagicMock()

    operations.github.repositories.repository.return_value = {
        "default_branch": "main"
    }

    operations.github.branches.get_branch.return_value = {
        "commit": {
            "sha": "abc123"
        }
    }

    operations.create_feature_branch(
        "openai",
        "odin",
        "feature/test",
    )

    operations.github.branches.create_branch.assert_called_once_with(
        "openai",
        "odin",
        "feature/test",
        "abc123",
    )