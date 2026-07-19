from __future__ import annotations

from pathlib import Path

from .patch_engine import SafePatchEngine
from .template_engine import TemplateEngine


DEFAULT_TEMPLATE = '''"""
{{description}}
"""

from __future__ import annotations


{{body}}
'''


class PythonModuleGenerator:
    """
    Generates Python modules from reusable templates.
    """

    def __init__(self):
        self.engine = TemplateEngine()

    def generate(
        self,
        path: Path,
        *,
        description: str,
        body: str,
    ) -> Path:

        text = self.engine.render(
            DEFAULT_TEMPLATE,
            {
                "description": description,
                "body": body,
            },
        )

        patch = SafePatchEngine(path)
        patch.text = text
        patch.write()

        return Path(path)
