from __future__ import annotations

import ast


class ScopeTracker(ast.NodeVisitor):
    """
    Tracks lexical scope while walking an AST.

    Maintains the current module/class/function nesting and
    records locally defined names for each scope.
    """

    def __init__(self) -> None:
        self.scope_stack: list[str] = []
        self.locals_stack: list[set[str]] = []

    def walk(self, tree: ast.AST) -> None:
        self.scope_stack.clear()
        self.locals_stack.clear()

        self.locals_stack.append(set())

        self.visit(tree)

    @property
    def current_scope(self) -> str:
        return ".".join(self.scope_stack)

    @property
    def current_locals(self) -> set[str]:
        return self.locals_stack[-1]

    #
    # Scope management
    #

    def _enter_scope(self, name: str) -> None:
        self.scope_stack.append(name)
        self.locals_stack.append(set())

    def _leave_scope(self) -> None:
        self.scope_stack.pop()
        self.locals_stack.pop()

    #
    # Definitions
    #

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.current_locals.add(node.name)

        self._enter_scope(node.name)
        self.generic_visit(node)
        self._leave_scope()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.current_locals.add(node.name)

        self._enter_scope(node.name)

        for arg in node.args.args:
            self.current_locals.add(arg.arg)

        self.generic_visit(node)

        self._leave_scope()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.current_locals.add(target.id)

        self.generic_visit(node)
