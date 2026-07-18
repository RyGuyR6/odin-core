from __future__ import annotations

import ast

from app.repository.models import ImportSymbol


class ImportExtractor(ast.NodeVisitor):
    """
    Extract import statements from a Python AST.
    """

    def __init__(self) -> None:
        self._imports: list[ImportSymbol] = []

    def extract(self, tree: ast.AST) -> list[ImportSymbol]:
        self._imports.clear()
        self.visit(tree)
        return list(self._imports)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._imports.append(
                ImportSymbol(
                    module=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""

        for alias in node.names:
            self._imports.append(
                ImportSymbol(
                    module=module,
                    name=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )

        self.generic_visit(node)
