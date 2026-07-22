from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import repositories as repositories_api
from app.auth import Principal, UserPublic, UserRole, get_current_principal
from app.services import repository_intelligence as intelligence_module


def create_sample_repository(root: Path) -> Path:
    (root / "backend/app").mkdir(parents=True)
    (root / "frontend/components").mkdir(parents=True)
    (root / "frontend/app/api/health").mkdir(parents=True)
    (root / "README.md").write_text(
        "# sample-repo\n\nSample repository for repository intelligence tests.\n"
    )
    (root / "docs").mkdir(parents=True)
    (root / "docs/architecture.md").write_text(
        "# Architecture\n\nHealth route uses backend services.\n"
    )
    (root / ".env.example").write_text("ODIN_ENV=test\n")
    (root / "pyproject.toml").write_text("""
[project]
name = "sample-repo"
dependencies = ["fastapi", "pydantic"]

[tool.pytest.ini_options]
addopts = "-q"
""".strip())
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "sample-repo",
                "scripts": {"build": "next build", "test": "vitest run"},
                "dependencies": {"next": "1.0.0", "react": "1.0.0"},
                "devDependencies": {"vitest": "1.0.0"},
            }
        )
    )
    (root / "backend/app/main.py").write_text("""
from fastapi import APIRouter
from .service import build_message

router = APIRouter()

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": build_message()}
""".strip())
    (root / "backend/app/service.py").write_text("""
\"\"\"Health service helpers.\"\"\"

from .models import STATUS_MESSAGE


def build_message() -> str:
    \"\"\"Build the outward-facing health response.\"\"\"
    return STATUS_MESSAGE
""".strip())
    (root / "backend/app/models.py").write_text("""
STATUS_MESSAGE = "ok"
""".strip())
    (root / "backend/app/cycle_a.py").write_text("from .cycle_b import helper_b\n")
    (root / "backend/app/cycle_b.py").write_text("from .cycle_a import helper_a\n")
    (root / "frontend/components/widget.tsx").write_text("""
export interface WidgetProps { label: string }
export const DEFAULT_LABEL = "ready"
export function Widget({ label }: WidgetProps) {
  return <div>{label}</div>;
}
""".strip())
    (root / "frontend/app/page.tsx").write_text("""
import { Widget, DEFAULT_LABEL } from "../components/widget";

export default function Page() {
  return <Widget label={DEFAULT_LABEL} />;
}
""".strip())
    (root / "frontend/app/api/health/route.ts").write_text("""
export async function GET() {
  return Response.json({ ok: true });
}
""".strip())
    return root


def admin_principal() -> Principal:
    return Principal(
        user=UserPublic(
            id="user-1",
            username="admin",
            email="admin@example.com",
            display_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            last_login_at=None,
            metadata={},
        ),
        method="test",
    )


async def fake_github_get(path: str, params=None):
    if path == "/user/repos":
        return [
            {
                "id": 1,
                "full_name": "acme/repo",
                "owner": {"login": "acme"},
                "name": "repo",
                "private": False,
                "default_branch": "main",
                "html_url": "https://github.com/acme/repo",
                "description": "Sample repository",
            }
        ]
    if path == "/repos/acme/repo":
        return {
            "id": 1,
            "full_name": "acme/repo",
            "owner": {"login": "acme"},
            "name": "repo",
            "private": False,
            "default_branch": "main",
            "html_url": "https://github.com/acme/repo",
            "description": "Sample repository",
            "archived": False,
            "disabled": False,
            "open_issues_count": 0,
            "pushed_at": "2026-07-21T00:00:00Z",
        }
    raise AssertionError(path)


def test_repository_intelligence_service_scans_repository(
    tmp_path: Path, monkeypatch
) -> None:
    root = create_sample_repository(tmp_path / "repo")
    monkeypatch.setenv("ODIN_REPOSITORY_SCAN_ROOTS", str(tmp_path))
    monkeypatch.setattr(intelligence_module, "DB_PATH", tmp_path / "odin.db")

    service = intelligence_module.RepositoryIntelligenceService()
    record = service.scan_repository("acme/repo", str(root))

    assert record.status == "ready"
    assert record.payload is not None
    assert "Python" in record.payload.summary.languages
    assert "TypeScript" in record.payload.summary.languages
    assert "FastAPI" in record.payload.summary.frameworks
    assert "Next.js" in record.payload.summary.frameworks
    assert any(
        category.category == "api_routes" for category in record.payload.architecture
    )
    assert any(symbol.qualified_name == "Widget" for symbol in record.payload.symbols)
    assert any(symbol.kind == "interface" for symbol in record.payload.symbols)
    assert any(
        document.path == "README.md" for document in record.payload.documentation
    )
    assert any(
        document.symbol == "build_message" for document in record.payload.documentation
    )
    assert any(
        reference.symbol == "STATUS_MESSAGE" for reference in record.payload.references
    )
    assert any(
        sorted(cycle) == ["backend/app/cycle_a.py", "backend/app/cycle_b.py"]
        for cycle in record.payload.dependency_graph.circular_dependencies
    )


def test_repository_intelligence_incremental_metadata_tracks_changes(
    tmp_path: Path, monkeypatch
) -> None:
    root = create_sample_repository(tmp_path / "repo")
    monkeypatch.setenv("ODIN_REPOSITORY_SCAN_ROOTS", str(tmp_path))
    monkeypatch.setattr(intelligence_module, "DB_PATH", tmp_path / "odin.db")

    service = intelligence_module.RepositoryIntelligenceService()
    first = service.scan_repository("acme/repo", str(root))
    assert first.payload is not None

    (root / "backend/app/service.py").write_text("""
\"\"\"Health service helpers.\"\"\"

from .models import STATUS_MESSAGE


def build_message() -> str:
    \"\"\"Build the updated health response.\"\"\"
    return STATUS_MESSAGE.upper()
""".strip())
    (root / "frontend/components/widget.tsx").unlink()

    second = service.scan_repository("acme/repo", str(root))
    assert second.payload is not None
    assert "backend/app/service.py" in second.payload.metadata["changed_files"]
    assert "frontend/components/widget.tsx" in second.payload.metadata["deleted_files"]
    assert not any(
        symbol.file_path == "frontend/components/widget.tsx"
        for symbol in second.payload.symbols
    )


def test_repository_intelligence_api_endpoints(tmp_path: Path, monkeypatch) -> None:
    root = create_sample_repository(tmp_path / "repo")
    monkeypatch.setenv("ODIN_REPOSITORY_SCAN_ROOTS", str(tmp_path))
    monkeypatch.setattr(intelligence_module, "DB_PATH", tmp_path / "odin.db")
    monkeypatch.setattr(repositories_api, "DB_PATH", tmp_path / "odin.db")
    monkeypatch.setattr(repositories_api, "_github_get", fake_github_get)

    app = FastAPI()
    app.dependency_overrides[get_current_principal] = admin_principal
    app.include_router(repositories_api.router)
    client = TestClient(app)

    connected = client.post(
        "/api/repositories",
        json={"full_name": "acme/repo", "local_path": str(root)},
    )
    assert connected.status_code == 201
    assert connected.json()["local_path"] == str(root)

    scanned = client.post("/api/repositories/acme/repo/scan", json={})
    assert scanned.status_code == 200
    assert scanned.json()["status"] == "ready"

    status = client.get("/api/repositories/acme/repo/status")
    assert status.status_code == 200
    assert status.json()["intelligence"]["status"] == "ready"
    assert status.json()["intelligence"]["summary"]["project_purpose"].startswith(
        "Sample repository"
    )

    summary = client.get("/api/repositories/acme/repo/summary")
    assert summary.status_code == 200
    assert "Next.js" in summary.json()["frameworks"]

    tree = client.get("/api/repositories/acme/repo/tree")
    assert tree.status_code == 200
    assert any(child["name"] == "backend" for child in tree.json()["children"])

    symbols = client.get("/api/repositories/acme/repo/symbols?q=Widget")
    assert symbols.status_code == 200
    assert symbols.json()["count"] >= 1
    assert any(item["qualified_name"] == "Widget" for item in symbols.json()["symbols"])

    graph = client.get("/api/repositories/acme/repo/dependency-graph")
    assert graph.status_code == 200
    assert any(
        edge["source"] == "frontend/app/page.tsx" for edge in graph.json()["edges"]
    )

    docs = client.get("/api/repositories/acme/repo/documentation?q=health")
    assert docs.status_code == 200
    assert docs.json()["count"] >= 1

    search = client.get("/api/repositories/acme/repo/search?q=health")
    assert search.status_code == 200
    assert search.json()["count"] >= 1

    context = client.get(
        "/api/repositories/acme/repo/context?q=Update the health route"
    )
    assert context.status_code == 200
    assert context.json()["repository"] == "acme/repo"
    assert context.json()["relevant_files"]

    references = client.get(
        "/api/repositories/acme/repo/references?symbol=STATUS_MESSAGE"
    )
    assert references.status_code == 200
    assert references.json()["count"] >= 1

    file_response = client.get(
        "/api/repositories/acme/repo/files?path=backend/app/service.py"
    )
    assert file_response.status_code == 200
    assert "build_message" in file_response.json()["content"]

    impact = client.get(
        "/api/repositories/acme/repo/impact?path=backend/app/service.py"
    )
    assert impact.status_code == 200
    assert "backend/app/main.py" in impact.json()["dependents"]
