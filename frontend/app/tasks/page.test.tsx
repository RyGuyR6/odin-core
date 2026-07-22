import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import TasksPage from "@/app/tasks/page";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const tasks = [
  {
    id: "task-1",
    title: "Dry run",
    description: "Preview change",
    status: "planned",
    approval_status: "pending",
    dry_run: true,
    confirmed: false,
    created_at: "2026-07-21T00:00:00Z",
    updated_at: "2026-07-21T00:00:00Z",
    steps: [{ id: "step-1", action: "echo", parameters: { message: "hello" } }],
  },
];

const workspaces = [
  {
    id: "workspace-1",
    task_id: "task-1",
    repository_id: 1,
    repository_full_name: "acme/repo",
    source_branch: "main",
    base_commit_sha: "1234567890abcdef",
    workspace_ref: "workspace-1",
    status: "awaiting_approval",
    created_at: "2026-07-21T00:00:00Z",
    updated_at: "2026-07-21T00:00:00Z",
    proposals: [
      {
        id: "proposal-1",
        target_path: "src/hello.py",
        operation: "modify_file",
        approval_status: "pending",
        reason: "Update greeting",
        diff_stats: { added_lines: 1, removed_lines: 1, language: "Python" },
      },
    ],
    approvals: [],
    validation_runs: [
      {
        id: "validation-1",
        command_id: "backend_test",
        label: "Backend tests",
        status: "succeeded",
        stdout: "passed",
        stderr: "",
        duration_ms: 25,
        timestamp: "2026-07-21T00:05:00Z",
      },
    ],
    rollback_history: [],
    audit_history: [
      {
        id: "audit-1",
        timestamp: "2026-07-21T00:01:00Z",
        action: "proposal.upserted",
        actor: "coder",
        note: null,
      },
    ],
    apply_results: [],
  },
];

const repositories = {
  repositories: [{ id: 1, full_name: "acme/repo", default_branch: "main" }],
};

const diff = {
  workspace_id: "workspace-1",
  full_diff: "--- a/src/hello.py\n+++ b/src/hello.py\n@@ -1 +1 @@\n-print('hello')\n+print('workspace')",
  truncated: false,
  summary: { changed_files: 1, added_lines: 1, removed_lines: 1 },
  files: [
    {
      proposal_id: "proposal-1",
      path: "src/hello.py",
      operation: "modify_file",
      diff: "@@ -1 +1 @@\n-print('hello')\n+print('workspace')",
      added_lines: 1,
      removed_lines: 1,
      language: "Python",
    },
  ],
};

const validationCommands = {
  commands: {
    backend_test: {
      id: "backend_test",
      label: "Backend tests",
      argv: ["make", "-C", "backend", "test"],
      cwd: ".",
    },
  },
};

function installFetchMock() {
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";

    if (url === "/api/change-tasks/" && method === "GET") return jsonResponse(tasks);
    if (url === "/api/change-tasks/workspaces" && method === "GET") return jsonResponse({ workspaces });
    if (url === "/api/repositories" && method === "GET") return jsonResponse(repositories);
    if (url === "/api/change-tasks/workspaces/workspace-1/diff" && method === "GET") return jsonResponse(diff);
    if (url === "/api/change-tasks/workspaces/workspace-1/validation-commands" && method === "GET") return jsonResponse(validationCommands);
    if (url === "/api/change-tasks/workspaces/workspace-1/approve" && method === "POST") return jsonResponse(workspaces[0]);
    if (url === "/api/change-tasks/workspaces/workspace-1/apply" && method === "POST") return jsonResponse(workspaces[0]);
    if (url === "/api/change-tasks/workspaces/workspace-1/validate" && method === "POST") return jsonResponse({ workspace_id: "workspace-1", status: "completed", runs: [] });
    if (url === "/api/change-tasks/workspaces/workspace-1/rollback" && method === "POST") return jsonResponse(workspaces[0]);
    throw new Error(`Unhandled request: ${method} ${url}`);
  }) as typeof fetch;
}

describe("TasksPage", () => {
  beforeEach(() => {
    installFetchMock();
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders workspace details and posts approval/apply/validate/rollback actions", async () => {
    render(<TasksPage />);

    expect(await screen.findByText("Tasks & Workspaces")).toBeInTheDocument();
    expect((await screen.findAllByText("acme/repo")).length).toBeGreaterThan(0);
    expect(await screen.findByText("src/hello.py")).toBeInTheDocument();
    expect(await screen.findByText("Update greeting")).toBeInTheDocument();
    expect(await screen.findByText("passed")).toBeInTheDocument();
    expect((await screen.findAllByText(/print\('workspace'\)/)).length).toBeGreaterThan(0);

    await userEvent.click(screen.getAllByRole("button", { name: "Approve" })[0]);
    await userEvent.click(screen.getByRole("button", { name: "Apply approved changes" }));
    await userEvent.click(screen.getByRole("button", { name: "Run default validation" }));
    await userEvent.click(screen.getByRole("button", { name: "Rollback" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/change-tasks/workspaces/workspace-1/approve",
        expect.objectContaining({ method: "POST" }),
      );
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/change-tasks/workspaces/workspace-1/apply",
        expect.objectContaining({ method: "POST" }),
      );
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/change-tasks/workspaces/workspace-1/validate",
        expect.objectContaining({ method: "POST" }),
      );
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/change-tasks/workspaces/workspace-1/rollback",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
