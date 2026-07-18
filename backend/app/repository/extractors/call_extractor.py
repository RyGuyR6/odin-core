from __future__ import annotations

import ast


class CallExtractor(ast.NodeVisitor):
    """
    Extracts function/method call relationships from an AST.

    Produces tuples of:
        (caller, callee)
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._current_scope: str | None = None

    def extract(self, tree: ast.AST) -> list[tuple[str, str]]:
        self.calls.clear()
        self._current_scope = None
        self.visit(tree)
        return list(self.calls)

    #
    # Scope tracking
    #

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self._current_scope
        self._current_scope = node.name
        self.generic_visit(node)
        self._current_scope = previous

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        previous = self._current_scope
        self._current_scope = node.name
        self.generic_visit(node)
        self._current_scope = previous

    #
    # Call extraction
    #

    def visit_Call(self, node: ast.Call) -> None:
        if self._current_scope is not None:
            callee = self._resolve_name(node.func)
            if callee:
                self.calls.append(
                    (
                        self._current_scope,
                        callee,
                    )
                )

        self.generic_visit(node)

    def _resolve_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            parts: list[str] = []

            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value

            if isinstance(node, ast.Name):
                parts.append(node.id)

            return ".".join(reversed(parts))

        return None
