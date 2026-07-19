from __future__ import annotations

from pathlib import Path


class SafePatchEngine:
    """
    Idempotent helper for safely modifying text files.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

        if self.path.exists():
            self.text = self.path.read_text(encoding="utf-8")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.text = ""

    def prepend_once(self, snippet: str) -> None:
        if snippet not in self.text:
            self.text = snippet + self.text

    def append_once(self, snippet: str) -> None:
        if snippet not in self.text:
            if self.text and not self.text.endswith("\n"):
                self.text += "\n"
            self.text += snippet

    def replace_once(self, old: str, new: str) -> bool:
        if old not in self.text:
            return False

        self.text = self.text.replace(old, new, 1)
        return True

    def ensure_contains(self, snippet: str) -> None:
        if snippet not in self.text:
            self.append_once(snippet)

    def write(self) -> None:
        self.path.write_text(self.text, encoding="utf-8")
