from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from typing import Any


class PromptCache:
    def __init__(self, max_size: int = 256):
        self.max_size = max(0, max_size)
        self._items: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str):
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return deepcopy(self._items[key])

    def set(self, key: str, value: Any) -> None:
        if self.max_size <= 0:
            return
        self._items[key] = deepcopy(value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def size(self) -> int:
        return len(self._items)
