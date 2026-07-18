import ast
from pathlib import Path

from app.repository.parser import RepositoryParser


def test_parse_returns_ast():

    parser = RepositoryParser()

    tree = parser.parse(Path(__file__))

    assert isinstance(tree, ast.Module)


def test_ast_contains_functions():

    parser = RepositoryParser()

    tree = parser.parse(Path(__file__))

    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    ]

    assert len(functions) >= 2
