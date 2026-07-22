"""Captures repository insights into persistent memory when a workspace is indexed."""

from __future__ import annotations

import logging
from typing import Any

from .manager import MemoryManager, get_memory_manager
from .models import MemoryCreate

log = logging.getLogger(__name__)


def capture_repository_insights(
    workspace_id: str,
    workspace_name: str,
    manifest: Any,
    manager: MemoryManager | None = None,
) -> list[str]:
    """Store repository discoveries as memory entries after indexing.

    Returns the list of memory IDs created (empty if manifest is None or
    has no useful data).
    """
    if manager is None:
        manager = get_memory_manager()

    if manifest is None:
        return []

    created: list[str] = []

    try:
        manifest_dict: dict[str, Any] = (
            manifest if isinstance(manifest, dict) else manifest.model_dump(mode="json")
        )
        summary = manifest_dict.get("summary") or {}
        project_purpose = summary.get("project_purpose", "")
        languages: list[str] = summary.get("languages", [])
        frameworks: list[str] = summary.get("frameworks", [])
        architecture: list[str] = summary.get("architecture", [])
        major_modules: list[dict] = summary.get("major_modules", [])
        files_indexed: int = manifest_dict.get("files_indexed", 0)
        total_bytes: int = manifest_dict.get("total_bytes", 0)

        if not project_purpose and not frameworks and not languages:
            return []

        # --- Repository summary memory ---
        parts = []
        if project_purpose:
            parts.append(f"Purpose: {project_purpose}")
        if languages:
            parts.append(f"Languages: {', '.join(languages)}")
        if frameworks:
            parts.append(f"Frameworks: {', '.join(frameworks)}")
        if architecture:
            parts.append(f"Architecture patterns: {', '.join(architecture)}")
        if major_modules:
            module_names = [m.get("name", "") for m in major_modules if m.get("name")]
            if module_names:
                parts.append(f"Major modules: {', '.join(module_names)}")
        parts.append(f"Files indexed: {files_indexed}, Size: {total_bytes:,} bytes")

        summary_content = "\n".join(parts)
        mem = manager.create(
            MemoryCreate(
                content=summary_content,
                title=f"Repository: {workspace_name}",
                kind="repository_discovery",
                scope="global",
                repository_id=workspace_id,
                source=f"repository_indexer:{workspace_id}",
                tags=["repository", "discovery", workspace_name] + frameworks[:4] + languages[:4],
                metadata={
                    "workspace_id": workspace_id,
                    "workspace_name": workspace_name,
                    "files_indexed": files_indexed,
                    "total_bytes": total_bytes,
                    "languages": languages,
                    "frameworks": frameworks,
                    "architecture": architecture,
                },
                importance=0.8,
                confidence=0.95,
                deduplicate=True,
            )
        )
        created.append(mem.id)

        # --- Architecture decisions memory (one per architecture pattern) ---
        for pattern in architecture[:5]:
            if not pattern:
                continue
            arch_content = (
                f"Repository '{workspace_name}' uses the '{pattern}' architectural pattern.\n"
                f"Frameworks: {', '.join(frameworks) or 'none detected'}"
            )
            try:
                mem = manager.create(
                    MemoryCreate(
                        content=arch_content,
                        title=f"Architecture: {pattern} in {workspace_name}",
                        kind="architecture_decision",
                        scope="global",
                        repository_id=workspace_id,
                        source=f"repository_indexer:{workspace_id}",
                        tags=["architecture", pattern.replace(" ", "_"), workspace_name],
                        metadata={
                            "workspace_id": workspace_id,
                            "workspace_name": workspace_name,
                            "pattern": pattern,
                        },
                        importance=0.75,
                        confidence=0.9,
                        deduplicate=True,
                    )
                )
                created.append(mem.id)
            except Exception:
                log.debug("Skipped architecture memory for pattern %r", pattern)

    except Exception:
        log.exception("Failed to capture repository insights for workspace %r", workspace_id)

    return created
