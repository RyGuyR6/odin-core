from __future__ import annotations


class IRAnalysisAdapter:
    """
    Executes analysis passes using the repository's IR.

    This adapter provides a stable integration point between the
    Repository IR and the Analysis Framework.
    """

    def __init__(self, repository):
        self._repository = repository

    @property
    def modules(self):
        return self._repository.ir

    def run(self):
        """
        Ensure the IR is available, then execute the analysis pipeline.
        """
        if not self._repository.ir:
            self._repository.build_ir()

        return self._repository.analysis.run(self._repository)
