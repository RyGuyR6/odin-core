from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PromptSettings:
    templates_dir: Path = field(default_factory=lambda: Path(
        os.getenv("ODIN_PROMPTS_DIR", Path(__file__).resolve().parent / "templates")
    ))
    cache_size: int = field(default_factory=lambda: int(os.getenv("ODIN_PROMPT_CACHE_SIZE", "256")))
    strict_by_default: bool = field(
        default_factory=lambda: os.getenv("ODIN_PROMPT_STRICT", "true").lower() in {"1", "true", "yes"}
    )
    auto_reload: bool = field(
        default_factory=lambda: os.getenv("ODIN_PROMPT_AUTO_RELOAD", "false").lower() in {"1", "true", "yes"}
    )


def get_prompt_settings() -> PromptSettings:
    return PromptSettings()
