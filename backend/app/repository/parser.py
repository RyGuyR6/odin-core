from __future__ import annotations

import ast
from pathlib import Path


class RepositoryParser:
    """
    Responsible only for parsing Python source into an AST.
    """

    def parse(self, file: Path) -> ast.Module:
        source = file.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file))

    def parse_source(self, source: str, filename: str = "<string>") -> ast.Module:
        return ast.parse(source, filename=filename)
