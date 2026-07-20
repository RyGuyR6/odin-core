from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import urlparse
from .exceptions import UnsafeRepositoryError

_SCP_LIKE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+$")

def validate_repository_url(value: str) -> str:
    value = value.strip()
    if _SCP_LIKE.match(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "ssh", "git", "file"}:
        raise UnsafeRepositoryError("Repository URL must use https, ssh, git, or file")
    if parsed.username and parsed.password:
        raise UnsafeRepositoryError("Credentials must not be embedded in repository URLs")
    return value

def safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise UnsafeRepositoryError(f"Path escapes workspace: {relative}") from exc
    return candidate

def validate_ref(ref: str) -> str:
    ref = ref.strip()
    if not ref or ref.startswith("-") or ".." in ref or ref.endswith(".lock"):
        raise UnsafeRepositoryError(f"Unsafe Git ref: {ref}")
    if any(ch in ref for ch in [" ", "~", "^", ":", "?", "*", "[", "\\"]):
        raise UnsafeRepositoryError(f"Unsafe Git ref: {ref}")
    return ref
