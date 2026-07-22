from __future__ import annotations

from abc import ABC, abstractmethod
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ParsedRepositoryDocument:
    path: str
    parser: str
    kind: str
    language: str | None = None
    tree: ast.Module | None = None
    text: str | None = None


class RepositoryLanguageParser(ABC):
    name: str

    @abstractmethod
    def supports(self, path: Path, language: str | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse(
        self,
        path: Path,
        source: str,
        *,
        language: str | None = None,
    ) -> ParsedRepositoryDocument:
        raise NotImplementedError


class PythonAstParser(RepositoryLanguageParser):
    name = "python_ast"

    def supports(self, path: Path, language: str | None = None) -> bool:
        return path.suffix.lower() == ".py" or (language or "").lower() == "python"

    def parse(
        self,
        path: Path,
        source: str,
        *,
        language: str | None = None,
    ) -> ParsedRepositoryDocument:
        return ParsedRepositoryDocument(
            path=path.as_posix(),
            parser=self.name,
            kind="python_ast",
            language=language,
            tree=ast.parse(source, filename=str(path)),
            text=source,
        )


class SafeTextParser(RepositoryLanguageParser):
    name = "safe_text"

    def supports(self, path: Path, language: str | None = None) -> bool:
        return True

    def parse(
        self,
        path: Path,
        source: str,
        *,
        language: str | None = None,
    ) -> ParsedRepositoryDocument:
        return ParsedRepositoryDocument(
            path=path.as_posix(),
            parser=self.name,
            kind="text",
            language=language,
            text=source,
        )


class RepositoryParser:
    """
    Resolves a language-aware parser and falls back to safe text parsing.
    """

    def __init__(
        self,
        parsers: list[RepositoryLanguageParser] | None = None,
        fallback: RepositoryLanguageParser | None = None,
    ) -> None:
        self._parsers = parsers or [PythonAstParser()]
        self._fallback = fallback or SafeTextParser()

    def parse(self, file: Path) -> ast.Module:
        source = file.read_text(encoding="utf-8")
        document = self.parse_document(file, source)
        return self._require_tree(document, file.as_posix())

    def parse_source(self, source: str, filename: str = "<string>") -> ast.Module:
        path = Path(filename)
        document = self.parse_document(path, source, language="Python")
        return self._require_tree(document, path.as_posix())

    def parse_document(
        self,
        path: str | Path,
        source: str,
        *,
        language: str | None = None,
    ) -> ParsedRepositoryDocument:
        file_path = Path(path)
        parser = self.select_parser(file_path, language)
        return parser.parse(file_path, source, language=language)

    def select_parser(
        self,
        path: str | Path,
        language: str | None = None,
    ) -> RepositoryLanguageParser:
        file_path = Path(path)
        for parser in self._parsers:
            if parser.supports(file_path, language):
                return parser
        return self._fallback

    @staticmethod
    def _require_tree(document: ParsedRepositoryDocument, path: str) -> ast.Module:
        if document.tree is None:
            raise ValueError(f"Language-aware AST is unavailable for {path}.")
        return document.tree
