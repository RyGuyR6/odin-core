from __future__ import annotations

import ast
from pathlib import Path

from app.repository.extractors import (
    CallExtractor,
    ImportExtractor,
    SymbolExtractor,
)
from app.repository.graph import (
    CallGraph,
    ImportGraph,
)
from app.repository.index import SymbolIndex
from app.repository.loader import RepositoryLoader
from app.repository.models import (
    RepositoryFile,
    RepositorySymbol,
)
from app.repository.parser import RepositoryParser
from app.repository.query import RepositoryQuery
from app.repository.analysis import AnalysisPipeline
from app.repository.ir import IRBuilder
from app.repository.ir import IRQuery
from app.repository.ir import IRAnalysisAdapter
from app.repository.resolution import (
    ResolutionContext,
    ResolutionEngine,
    SymbolResolver,
)


class Repository:

    def __init__(self, root: str | Path):

        self.root = Path(root).resolve()

        self.loader = RepositoryLoader(self.root)
        self.parser = RepositoryParser()

        self.symbol_extractor = SymbolExtractor()
        self.import_extractor = ImportExtractor()
        self.call_extractor = CallExtractor()

        self._index = SymbolIndex()
        self.index_db = self._index

        self.import_graph = ImportGraph()
        self.call_graph = CallGraph()

        self.query = RepositoryQuery(
            self._index,
            self.import_graph,
            self.call_graph,
        )

        self.analysis = AnalysisPipeline()
        self.ir_builder = IRBuilder()
        self.ir_modules = []
        self.ir_query = IRQuery(self.ir_modules)
        self.ir_analysis = IRAnalysisAdapter(self)

        self.resolver = SymbolResolver(
            self._index,
        )

        self.resolution_engine = ResolutionEngine(
            self.resolver,
        )

        self.files: list[RepositoryFile] = []
        self.trees: dict[Path, ast.Module] = {}

    def load(self) -> list[RepositoryFile]:
        self.files = self.loader.load()
        return self.files

    def parse(self) -> dict[Path, ast.Module]:

        if not self.files:
            self.load()

        self.trees.clear()

        for file in self.files:
            self.trees[file.path] = self.parser.parse(file.path)

        return self.trees

    def index(self) -> SymbolIndex:

        if not self.trees:
            self.parse()

        self._index.clear()
        self.import_graph.clear()
        self.call_graph.clear()

        for file in self.files:

            tree = self.trees[file.path]

            #
            # Symbols
            #

            symbols = self.symbol_extractor.extract(
                tree,
                module=file.module,
                file=file.path,
            )

            for symbol in symbols:
                self._index.add(symbol)

            #
            # Imports
            #

            imports = self.import_extractor.extract(tree)

            for imp in imports:
                self.import_graph.add(
                    file.module,
                    imp.module,
                )

            #
            # Calls
            #

            calls = self.call_extractor.extract(tree)

            for caller, callee in calls:
                self.call_graph.add(
                    caller,
                    callee,
                )

        return self._index

    def refresh(self) -> None:
        self.load()
        self.parse()
        self.index()

    #
    # Query API
    #

    def find_symbol(self, name: str) -> RepositorySymbol | None:
        return self.query.find_symbol(name)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self.query.all_symbols()

    def dependencies(self, module: str) -> list[str]:
        return self.query.dependencies(module)

    def dependents(self, module: str) -> list[str]:
        return self.query.dependents(module)

    def search(self, text: str):
        return self.query.search(text)

    def callers(self, callee: str) -> list[str]:
        return self.query.callers(callee)

    def callees(self, caller: str) -> list[str]:
        return self.query.callees(caller)

    def resolve(
        self,
        name: str,
        module: str = "",
    ):
        context = ResolutionContext(
            module=module,
            file=self.root,
        )

        return self.resolution_engine.resolve(
            name,
            context,
        )




    def build_ir(self):
        """
        Build IR for every parsed module.
        """
        self.ir_modules = []

        for path, tree in self._parsed.items():
            self.ir_modules.append(
                self.ir_builder.build_module(
                    path=path,
                    tree=tree,
                )
            )

        self.ir_query = IRQuery(self.ir_modules)
        self.ir_analysis = IRAnalysisAdapter(self)
        return self.ir_modules

    def analyze(self):
        """
        Execute all registered analysis passes.
        """
        return self.analysis.run(self)



    @property
    def ir(self):
        return self.ir_modules

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def parsed_count(self) -> int:
        return len(self.trees)

    @property
    def symbol_count(self) -> int:
        return len(self._index)
