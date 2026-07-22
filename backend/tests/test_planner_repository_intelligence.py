from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import planner as planner_api
from app.context.service import context_service
from app.planning.planner import Planner
from app.services import repository_intelligence as intelligence_module


def create_sample_repository(root: Path) -> Path:
    (root / "backend/app").mkdir(parents=True)
    (root / "frontend/app/api/health").mkdir(parents=True)
    (root / "frontend/components").mkdir(parents=True)

    (root / "README.md").write_text(
        "# sample-repo\n\nSample repository for planner tests.\n"
    )

    (root / "backend/pyproject.toml").write_text("""
[project]
name = "sample-repo"
dependencies = ["fastapi", "pydantic"]
""".strip())

    (root / "frontend/package.json").write_text(
        json.dumps(
            {
                "name": "sample-repo",
                "dependencies": {
                    "next": "1.0.0",
                    "react": "1.0.0",
                },
            }
        )
    )

    (root / "backend/app/main.py").write_text("""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
""".strip())

    (root / "backend/app/service.py").write_text("""
def build_health_message() -> str:
    return "ok"
""".strip())

    (root / "frontend/components/widget.tsx").write_text("""
export function HealthWidget() {
  return <div>ok</div>;
}
""".strip())

    (root / "frontend/app/api/health/route.ts").write_text("""
export async function GET() {
  return Response.json({ ok: true });
}
""".strip())

    return root


def test_planner_uses_repository_intelligence_for_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = create_sample_repository(tmp_path / "repo")
    monkeypatch.setenv("ODIN_REPOSITORY_SCAN_ROOTS", str(tmp_path))
    monkeypatch.setattr(intelligence_module, "DB_PATH", tmp_path / "odin.db")

    service = intelligence_module.RepositoryIntelligenceService()
    service.scan_repository("acme/repo", str(root))

    plan = Planner().create_plan(
        "Update the health API route",
        repository="acme/repo",
    )

    assert "review_repository_intelligence" in plan.metadata["phases"]
    assert "review_backend_surface" in plan.metadata["phases"]
    assert plan.metadata["repository"]["status"] == "ready"
    assert plan.metadata["repository_context"].startswith("Repository: acme/repo")
    assert plan.metadata["repository_package"]["repository"] == "acme/repo"
    assert "likely_tests" in plan.metadata
    assert any(
        candidate["path"] == "frontend/app/api/health/route.ts"
        for candidate in plan.metadata["candidate_files"]
    )


def test_planner_api_returns_repository_intelligence_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context_service.clear()
    root = create_sample_repository(tmp_path / "repo")
    monkeypatch.setenv("ODIN_REPOSITORY_SCAN_ROOTS", str(tmp_path))
    monkeypatch.setattr(intelligence_module, "DB_PATH", tmp_path / "odin.db")

    service = intelligence_module.RepositoryIntelligenceService()
    service.scan_repository("acme/repo", str(root))

    app = FastAPI()
    app.include_router(planner_api.router)
    client = TestClient(app)

    response = client.post(
        "/planner/",
        json={
            "goal": "Update the health API route",
            "repository": "acme/repo",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert "identify_candidate_files" in body["phases"]
    assert body["repository"]["status"] == "ready"
    assert body["repository_package"]["repository"] == "acme/repo"
    assert body["repository_summary"]["frameworks"] == [
        "FastAPI",
        "Next.js",
        "Pydantic",
        "React",
    ]
    assert "likely_tests" in body
    assert body["result"]["variables"]["repository"]["full_name"] == "acme/repo"
    assert any(
        candidate["path"] == "frontend/app/api/health/route.ts"
        for candidate in body["candidate_files"]
    )
