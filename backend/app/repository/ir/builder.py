from __future__ import annotations

import ast
from pathlib import Path

from .models import (
    IRClass,
    IRFunction,
    IRModule,
)


class IRBuilder:
    """
    Builds Odin IR from parsed Python ASTs.
    """

    def build_module(
        self,
        path: Path,
        tree: ast.AST,
    ) -> IRModule:

        module = IRModule(
            name=path.stem,
            path=path,
        )

        for node in tree.body:

            if isinstance(node, ast.FunctionDef):
                module.functions.append(
                    IRFunction(
                        name=node.name,
                        qualified_name=node.name,
                        line=node.lineno,
                    )
                )

            elif isinstance(node, ast.ClassDef):

                ir_class = IRClass(
                    name=node.name,
                    qualified_name=node.name,
                    line=node.lineno,
                )

                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        ir_class.methods.append(
                            IRFunction(
                                name=child.name,
                                qualified_name=f"{node.name}.{child.name}",
                                line=child.lineno,
                            )
                        )

                module.classes.append(ir_class)

        return module
