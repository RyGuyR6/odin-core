import { render, screen } from "@testing-library/react";
import ToolsPage from "@/app/tools/page";
import { vi } from "vitest";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("ToolsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders installed tools, approvals, and recent executions", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/api/tools") {
        return jsonResponse({
          tools: [
            {
              name: "terminal.execute",
              description: "Run a command",
              category: "terminal",
              version: "1.0.0",
              risk: "high",
              permission_level: "approval_required",
              requires_approval: true,
              required_permissions: ["tools.execute.terminal.execute"],
              max_retries: 0,
              tags: ["terminal"],
              capability_metadata: {},
            },
          ],
          count: 1,
        });
      }
      if (url === "/api/tools/telemetry") {
        return jsonResponse({
          total_executions: 4,
          succeeded: 2,
          failed: 1,
          cancelled: 0,
          timed_out: 0,
          awaiting_approval: 1,
          average_elapsed_ms: 120,
          tools_registered: 1,
        });
      }
      if (url === "/api/tools/executions?limit=12") {
        return jsonResponse({
          executions: [
            {
              id: "exec-1",
              tool_name: "terminal.execute",
              tool_version: "1.0.0",
              status: "awaiting_approval",
              risk: "high",
              arguments: {},
              actor_id: "odin",
              workspace_id: "default",
              created_at: "2026-07-22T00:00:00Z",
            },
          ],
          count: 1,
        });
      }
      if (url === "/api/tools/approvals?limit=8") {
        return jsonResponse({
          approvals: [
            {
              id: "approval-1",
              execution_id: "exec-1",
              tool_name: "terminal.execute",
              actor_id: "odin",
              reason: "terminal.execute requires approval",
              status: "pending",
              expires_at: "2026-07-23T00:00:00Z",
              created_at: "2026-07-22T00:00:00Z",
            },
          ],
          count: 1,
        });
      }
      if (url === "/api/tools/health") {
        return jsonResponse({
          tools: [
            {
              tool_name: "terminal.execute",
              category: "terminal",
              version: "1.0.0",
              status: "healthy",
              capability_metadata: {},
            },
          ],
          count: 1,
        });
      }
      if (url === "/api/tools/permissions") {
        return jsonResponse({
          shell_enabled: false,
          python_enabled: false,
          require_approval_for_writes: true,
          require_approval_for_shell: true,
          permissions: [
            {
              tool_name: "terminal.execute",
              category: "terminal",
              permission_level: "approval_required",
              required_permissions: ["tools.execute.terminal.execute"],
              risk: "high",
              requires_approval: true,
            },
          ],
        });
      }
      throw new Error(`Unhandled URL: ${url}`);
    }) as typeof fetch;

    render(<ToolsPage />);

    expect(await screen.findByText("Tool Manager")).toBeInTheDocument();
    expect((await screen.findAllByText("terminal.execute")).length).toBeGreaterThan(0);
    expect(screen.getByText("approval required")).toBeInTheDocument();
    expect(screen.getByText("terminal.execute requires approval")).toBeInTheDocument();
    expect(screen.getByText("Recent executions")).toBeInTheDocument();
  });
});
