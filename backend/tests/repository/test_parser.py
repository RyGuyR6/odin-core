import ast
from pathlib import Path

import pytest

from app.repository.parser import RepositoryParser


def test_parse_returns_ast():

    parser = RepositoryParser()

    tree = parser.parse(Path(__file__))

    assert isinstance(tree, ast.Module)


def test_ast_contains_functions():

    parser = RepositoryParser()

    tree = parser.parse(Path(__file__))

    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

    assert len(functions) >= 2


def test_parse_document_uses_language_aware_python_parser():

    parser = RepositoryParser()

    document = parser.parse_document(
        "sample.py",
        "def build_message() -> str:\n    return 'ok'\n",
        language="Python",
    )

    assert document.kind == "python_ast"
    assert document.parser == "python_ast"
    assert isinstance(document.tree, ast.Module)


def test_parse_document_falls_back_to_safe_text():

    parser = RepositoryParser()

    document = parser.parse_document(
        Path("README.md"),
        "# Sample\n\nRepository docs.\n",
        language="Markdown",
    )

    assert document.kind == "text"
    assert document.parser == "safe_text"
    assert document.tree is None
    assert "Repository docs" in (document.text or "")


def test_parse_raises_when_ast_is_unavailable(tmp_path: Path):

    parser = RepositoryParser()
    file = tmp_path / "README.md"
    file.write_text("# Sample\n")

    with pytest.raises(ValueError, match="AST is unavailable"):
        parser.parse(file)
