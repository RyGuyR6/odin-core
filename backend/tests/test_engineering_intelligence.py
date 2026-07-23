from __future__ import annotations

from pathlib import Path

import pytest

from app.services import repository_intelligence as intelligence_module
from app.services.engineering_intelligence import engineering_intelligence_service
from app.services.repository_intelligence import repository_intelligence_service
from tests.test_repository_intelligence import create_sample_repository


def _scan(tmp_path: Path, monkeypatch) -> Path:
    root = create_sample_repository(tmp_path / "repo")
    (root / "backend/app/large_service.py").write_text(
        "\n".join(
            [
                "# TODO: split this service",
                "def decide(value):",
                *[
                    f"    {'el' if index else ''}if value == {index}: return {index}"
                    for index in range(40)
                ],
                "    return -1",
                *["# filler" for _ in range(380)],
            ]
        )
    )
    monkeypatch.setenv("ODIN_REPOSITORY_SCAN_ROOTS", str(tmp_path))
    monkeypatch.setattr(intelligence_module, "DB_PATH", tmp_path / "odin.db")
    repository_intelligence_service.scan_repository("acme/repo", str(root))
    return root


def test_report_detects_architecture_debt_complexity_and_risk(
    tmp_path: Path, monkeypatch
) -> None:
    _scan(tmp_path, monkeypatch)

    report = engineering_intelligence_service.analyze(
        "acme/repo",
        paths=["backend/app/service.py"],
        objective="Change the health service",
    )

    assert report.repository == "acme/repo"
    assert report.architecture["languages"]
    assert report.detected_patterns
    assert any(
        item.path == "backend/app/large_service.py"
        for item in report.complexity_hotspots
    )
    assert any(item.id.startswith("cycle:") for item in report.technical_debt)
    assert any(item.id.startswith("todo:") for item in report.technical_debt)
    assert "backend/app/main.py" in report.impact.direct_dependents
    assert report.validation_recommendations
    assert report.metrics["files_analyzed"] > 0


def test_report_is_deterministic(tmp_path: Path, monkeypatch) -> None:
    _scan(tmp_path, monkeypatch)
    first = engineering_intelligence_service.analyze("acme/repo")
    second = engineering_intelligence_service.analyze("acme/repo")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_report_rejects_unknown_target(tmp_path: Path, monkeypatch) -> None:
    _scan(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not present"):
        engineering_intelligence_service.analyze(
            "acme/repo", paths=["missing/file.py"]
        )


def test_report_requires_ready_repository(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(intelligence_module, "DB_PATH", tmp_path / "odin.db")
    with pytest.raises(ValueError, match="not ready"):
        engineering_intelligence_service.analyze("acme/missing")


def test_report_rejects_stale_repository_index(tmp_path: Path, monkeypatch) -> None:
    root = _scan(tmp_path, monkeypatch)
    (root / "backend/app/service.py").write_text(
        "def build_message() -> str:\n    return 'changed after scan'\n"
    )

    with pytest.raises(ValueError, match="index is stale"):
        engineering_intelligence_service.analyze("acme/repo")


def test_transitive_dependents_exclude_direct_dependents(
    tmp_path: Path, monkeypatch
) -> None:
    root = _scan(tmp_path, monkeypatch)
    (root / "backend/app/consumer.py").write_text(
        "from .main import health\n"
    )
    repository_intelligence_service.scan_repository("acme/repo", str(root))

    report = engineering_intelligence_service.analyze(
        "acme/repo", paths=["backend/app/service.py"]
    )

    assert "backend/app/main.py" in report.impact.direct_dependents
    assert "backend/app/main.py" not in report.impact.transitive_dependents
    assert "backend/app/consumer.py" in report.impact.transitive_dependents
