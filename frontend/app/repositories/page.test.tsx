import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RepositoriesPage from "@/app/repositories/page";
import { vi } from "vitest";

type MockResponse = {
  ok?: boolean;
  status?: number;
  body?: unknown;
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const connectedRepository = {
  github_id: 1,
  full_name: "acme/repo",
  owner: "acme",
  name: "repo",
  private: false,
  default_branch: "main",
  html_url: "https://github.com/acme/repo",
  description: "Sample repository",
  local_path: "/workspace/acme/repo",
  scan_status: "ready",
  scan_completed_at: "2026-07-21T00:00:00Z",
};

const summary = {
  project_purpose: "Sample repository for repository intelligence tests.",
  languages: ["Python", "TypeScript"],
  frameworks: ["FastAPI", "Next.js"],
  architecture: ["api_routes", "components", "services"],
  major_modules: [{ name: "backend", file_count: 4 }],
  key_entry_points: ["backend/app/main.py", "frontend/app/page.tsx"],
  test_framework: ["pytest", "Vitest"],
  build_system: ["Make", "Next.js"],
  package_manager: ["Python", "npm"],
};

const architecture = [
  { category: "api_routes", files: ["backend/app/main.py", "frontend/app/api/health/route.ts"] },
  { category: "components", files: ["frontend/components/widget.tsx"] },
];

const tree = {
  name: "/",
  path: "",
  type: "directory",
  children: [
    { name: "backend", path: "backend", type: "directory", children: [] },
    { name: "frontend", path: "frontend", type: "directory", children: [] },
  ],
};

const graph = {
  nodes: [
    { id: "backend/app/main.py", label: "backend/app/main.py", kind: "file" },
    { id: "frontend/app/page.tsx", label: "frontend/app/page.tsx", kind: "file" },
  ],
  edges: [
    { source: "frontend/app/page.tsx", target: "frontend/components/widget.tsx", kind: "import", external: false },
  ],
  circular_dependencies: [["backend/app/cycle_a.py", "backend/app/cycle_b.py"]],
  entry_points: ["backend/app/main.py", "frontend/app/page.tsx"],
};

const symbols = {
  count: 1,
  symbols: [
    { name: "Widget", qualified_name: "Widget", kind: "function", file_path: "frontend/components/widget.tsx", line: 3 },
  ],
};

const documentation = {
  count: 1,
  documents: [
    { path: "README.md", line: 1, title: "sample-repo", kind: "documentation", excerpt: "Sample repository for repository intelligence tests." },
  ],
};

function installFetchMock(handler: (url: string, init?: RequestInit) => MockResponse) {
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const response = handler(url, init);
    return jsonResponse(response.body ?? {}, response.status ?? (response.ok === false ? 500 : 200));
  }) as typeof fetch;
}

describe("RepositoriesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders repository intelligence results for the selected repository", async () => {
    installFetchMock((url) => {
      if (url === "/api/repositories") return { body: { repositories: [connectedRepository] } };
      if (url === "/api/repositories/available") return { body: { repositories: [] } };
      if (url === "/api/repositories/acme/repo/status") {
        return {
          body: {
            connected: true,
            repository: connectedRepository,
            github: { default_branch: "main", private: false, archived: false, disabled: false, open_issues_count: 0, pushed_at: "2026-07-21T00:00:00Z" },
            intelligence: { status: "ready", local_path: connectedRepository.local_path, summary, architecture },
          },
        };
      }
      if (url === "/api/repositories/acme/repo/summary") return { body: summary };
      if (url === "/api/repositories/acme/repo/tree") return { body: tree };
      if (url === "/api/repositories/acme/repo/dependency-graph") return { body: graph };
      if (url === "/api/repositories/acme/repo/symbols") return { body: symbols };
      if (url === "/api/repositories/acme/repo/documentation") return { body: documentation };
      if (url === "/api/repositories/acme/repo/documentation?q=health") return { body: documentation };
      throw new Error(`Unhandled URL: ${url}`);
    });

    render(<RepositoriesPage />);

    expect(await screen.findByText("Repository Intelligence")).toBeInTheDocument();
    expect((await screen.findAllByText(summary.project_purpose)).length).toBeGreaterThan(0);
    expect(screen.getByText("FastAPI, Next.js")).toBeInTheDocument();
    expect(screen.getAllByText("backend/app/main.py").length).toBeGreaterThan(0);
    expect(screen.getAllByText("frontend/app/page.tsx").length).toBeGreaterThan(0);
    expect(screen.getByText("backend/app/cycle_a.py → backend/app/cycle_b.py")).toBeInTheDocument();
    expect(await screen.findByText("Widget")).toBeInTheDocument();
  });

  it("posts a scan request with the selected local path", async () => {
    installFetchMock((url, init) => {
      if (url === "/api/repositories") return { body: { repositories: [connectedRepository] } };
      if (url === "/api/repositories/available") return { body: { repositories: [] } };
      if (url === "/api/repositories/acme/repo/status") {
        return {
          body: {
            connected: true,
            repository: { ...connectedRepository, scan_status: "not_scanned" },
            github: { default_branch: "main", private: false, archived: false, disabled: false, open_issues_count: 0, pushed_at: "2026-07-21T00:00:00Z" },
            intelligence: { status: "not_scanned", local_path: connectedRepository.local_path, summary: null, architecture: [] },
          },
        };
      }
      if (url === "/api/repositories/acme/repo/scan") {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBe(JSON.stringify({ local_path: connectedRepository.local_path }));
        return {
          body: {
            repository: "acme/repo",
            status: "ready",
            payload: { summary, directory_tree: tree, architecture, dependency_graph: graph },
          },
        };
      }
      if (url === "/api/repositories/acme/repo/summary") return { body: summary };
      if (url === "/api/repositories/acme/repo/tree") return { body: tree };
      if (url === "/api/repositories/acme/repo/dependency-graph") return { body: graph };
      if (url === "/api/repositories/acme/repo/symbols") return { body: symbols };
      if (url === "/api/repositories/acme/repo/documentation") return { body: documentation };
      throw new Error(`Unhandled URL: ${url}`);
    });

    render(<RepositoriesPage />);
    const button = await screen.findByRole("button", { name: "Scan repository" });
    await userEvent.click(button);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/repositories/acme/repo/scan",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("starts async re-indexing and sends repository search filters", async () => {
    installFetchMock((url, init) => {
      if (url === "/api/repositories") return { body: { repositories: [connectedRepository] } };
      if (url === "/api/repositories/available") return { body: { repositories: [] } };
      if (url === "/api/repositories/acme/repo/status") {
        return {
          body: {
            connected: true,
            repository: connectedRepository,
            github: { default_branch: "main", private: false, archived: false, disabled: false, open_issues_count: 0, pushed_at: "2026-07-21T00:00:00Z" },
            intelligence: {
              status: "ready",
              local_path: connectedRepository.local_path,
              indexed_revision: "abcdef1234567890",
              summary,
              architecture,
              metadata: { indexed_branch: "main" },
            },
          },
        };
      }
      if (url === "/api/repositories/acme/repo/reindex") {
        expect(init?.method).toBe("POST");
        return {
          body: {
            repository: "acme/repo",
            local_path: connectedRepository.local_path,
            status: "scanning",
          },
        };
      }
      if (url === "/api/repositories/acme/repo/summary") return { body: summary };
      if (url === "/api/repositories/acme/repo/tree") return { body: tree };
      if (url === "/api/repositories/acme/repo/dependency-graph") return { body: graph };
      if (url === "/api/repositories/acme/repo/symbols") return { body: symbols };
      if (url === "/api/repositories/acme/repo/documentation") return { body: documentation };
      if (url === "/api/repositories/acme/repo/search?q=health&language=TypeScript&file_type=source&symbol_type=function&include_documentation=false") {
        return {
          body: {
            count: 1,
            results: [
              {
                repository: "acme/repo",
                file_path: "frontend/app/page.tsx",
                symbol: "Page",
                source_location: { line: 1 },
                relevance_score: 91.2,
                match_type: "symbol",
                excerpt: "function Page()",
                indexed_revision: "abcdef1234567890",
                language: "TypeScript",
                file_type: "source",
              },
            ],
            stale: false,
            indexed_revision: "abcdef1234567890",
            metrics: { search_latency_ms: 12.5, semantic_ranking_applied: true },
          },
        };
      }
      throw new Error(`Unhandled URL: ${url}`);
    });

    render(<RepositoriesPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Re-index" }));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/repositories/acme/repo/reindex",
        expect.objectContaining({ method: "POST" }),
      );
    });

    await userEvent.selectOptions(screen.getByLabelText("Language"), "TypeScript");
    await userEvent.selectOptions(screen.getByLabelText("File type"), "source");
    await userEvent.selectOptions(screen.getByLabelText("Symbol type"), "function");
    await userEvent.selectOptions(screen.getByLabelText("Documentation"), "false");
    await userEvent.type(screen.getByPlaceholderText("Search files, symbols, docs"), "health");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Search latency: 12.5 ms")).toBeInTheDocument();
    expect(screen.getByText("Semantic ranking: applied")).toBeInTheDocument();
  });
});
