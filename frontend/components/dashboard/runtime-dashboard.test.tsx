import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuntimeDashboard } from "@/components/dashboard/runtime-dashboard";
import { getRuntime, type RuntimeData } from "@/lib/api/runtime";
import { vi } from "vitest";

vi.mock("@/lib/api/runtime", () => ({
  getRuntime: vi.fn(),
}));

const mockedGetRuntime = vi.mocked(getRuntime);

function runtimeFixture(overrides: Partial<RuntimeData> = {}): RuntimeData {
  return {
    runtime: {
      status: "healthy",
      version: "1.2.3",
      environment: "test",
      uptime_seconds: 120,
      metrics: { cpu_percent: 11, memory_percent: 22, disk_percent: 33 },
    },
    agents: [
      { id: "planner", name: "Planner", status: "idle", description: "Plans work" },
      { id: "execution", name: "Execution", status: "running", description: "Runs tasks" },
      { id: "review", name: "Code Review", status: "idle", description: "Reviews code" },
      { id: "testing", name: "Testing", status: "idle", description: "Runs checks" },
      { id: "deployment", name: "Deployment", status: "idle", description: "Handles deploys" },
    ],
    tasks: { queued: 1, running: 2, completed: 3, failed: 4 },
    repositories: { connected: 2 },
    recent_activity: [{ id: "a1", timestamp: "2026-07-21T00:00:00.000Z", level: "info", message: "Syncing repository" }],
    proxy: { latencyMs: 5, checkedAt: "2026-07-21T01:00:00.000Z" },
    ...overrides,
  };
}

describe("RuntimeDashboard", () => {
  beforeEach(() => {
    mockedGetRuntime.mockReset();
  });

  it("shows loading state", () => {
    mockedGetRuntime.mockReturnValue(new Promise(() => {}));
    const { container } = render(<RuntimeDashboard />);
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(4);
  });

  it("shows API error state with retry", async () => {
    mockedGetRuntime.mockRejectedValueOnce(new Error("Runtime unavailable"));
    render(<RuntimeDashboard />);
    expect(await screen.findByText("Runtime unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("renders all five agents and task counters", async () => {
    mockedGetRuntime.mockResolvedValue(runtimeFixture());
    render(<RuntimeDashboard />);

    for (const name of ["Planner", "Execution", "Code Review", "Testing", "Deployment"]) {
      expect(await screen.findByText(name)).toBeInTheDocument();
    }
    const tasksSection = screen.getByText("Tasks").closest("article");
    expect(tasksSection).not.toBeNull();
    for (const [label, value] of Object.entries({ queued: 1, running: 2, completed: 3, failed: 4 })) {
      const card = within(tasksSection as HTMLElement).getByText(label).closest("div");
      expect(card).not.toBeNull();
      expect(within(card as HTMLElement).getByText(String(value))).toBeInTheDocument();
    }
  });

  it("updates when status changes", async () => {
    mockedGetRuntime.mockResolvedValueOnce(runtimeFixture()).mockResolvedValueOnce(runtimeFixture({
      runtime: { status: "degraded", version: "1.2.3", environment: "test", uptime_seconds: 120, metrics: { cpu_percent: 11, memory_percent: 22, disk_percent: 33 } },
    }));

    render(<RuntimeDashboard />);
    expect(await screen.findByText("healthy")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByText("degraded")).toBeInTheDocument();
  });

  it("does not show hardcoded operational offline statuses", async () => {
    mockedGetRuntime.mockResolvedValue(runtimeFixture());
    render(<RuntimeDashboard />);
    await screen.findByText("Planner");
    expect(screen.queryByText(/operational offline/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^offline$/i)).not.toBeInTheDocument();
  });

  it("shows current task and last heartbeat", async () => {
    mockedGetRuntime.mockResolvedValue(runtimeFixture());
    render(<RuntimeDashboard />);
    expect(await screen.findByText(/Current task: Syncing repository/)).toBeInTheDocument();
    expect(screen.getByText(/Last heartbeat:/)).toBeInTheDocument();
    expect(screen.queryByText(/Last heartbeat: Unavailable/)).not.toBeInTheDocument();
  });

  it("shows sanitized refresh errors", async () => {
    mockedGetRuntime
      .mockResolvedValueOnce(runtimeFixture())
      .mockRejectedValueOnce(new Error("<script>alert(1)</script>failed"));

    const { container } = render(<RuntimeDashboard />);
    await screen.findByText("Planner");
    await userEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByText(/Refresh failed: alert\(1\)failed\./)).toBeInTheDocument();
    });
    expect(container.querySelector("script")).toBeNull();
  });
});
