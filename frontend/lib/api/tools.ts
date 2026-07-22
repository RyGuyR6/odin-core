export type ToolDefinition = {
  name: string;
  description: string;
  category: string;
  version: string;
  risk: "low" | "medium" | "high" | "critical";
  permission_level: "safe" | "approval_required" | "restricted";
  requires_approval: boolean;
  required_permissions: string[];
  timeout_seconds?: number | null;
  max_retries: number;
  tags: string[];
  capability_metadata: Record<string, unknown>;
};

export type ToolExecution = {
  id: string;
  tool_name: string;
  tool_version: string;
  status: string;
  risk: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  error?: string | null;
  actor_id: string;
  agent_id?: string | null;
  workspace_id: string;
  approval_id?: string | null;
  approval_status?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_ms?: number | null;
  created_at: string;
};

export type ToolApproval = {
  id: string;
  execution_id: string;
  tool_name: string;
  actor_id: string;
  reason: string;
  status: string;
  expires_at: string;
  created_at: string;
  decided_at?: string | null;
  decided_by?: string | null;
  note?: string | null;
};

export type ToolHealth = {
  tool_name: string;
  category: string;
  version: string;
  status: string;
  detail?: string | null;
  capability_metadata: Record<string, unknown>;
};

export type ToolTelemetry = {
  total_executions: number;
  succeeded: number;
  failed: number;
  cancelled: number;
  timed_out: number;
  awaiting_approval: number;
  average_elapsed_ms: number;
  tools_registered: number;
};

export type ToolPermissionSummary = {
  tool_name: string;
  category: string;
  permission_level: "safe" | "approval_required" | "restricted";
  required_permissions: string[];
  risk: "low" | "medium" | "high" | "critical";
  requires_approval: boolean;
};

export type ToolManagerData = {
  tools: ToolDefinition[];
  telemetry: ToolTelemetry;
  executions: ToolExecution[];
  approvals: ToolApproval[];
  health: ToolHealth[];
  permissions: {
    shell_enabled: boolean;
    python_enabled: boolean;
    require_approval_for_writes: boolean;
    require_approval_for_shell: boolean;
    permissions: ToolPermissionSummary[];
  };
};

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/tools${path}`, {
    cache: "no-store",
    signal,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail ?? `Tool request failed (${response.status})`);
  }
  return body as T;
}

export async function getToolManagerData(signal?: AbortSignal): Promise<ToolManagerData> {
  const [tools, telemetry, executions, approvals, health, permissions] = await Promise.all([
    request<{ tools: ToolDefinition[]; count: number }>("", signal),
    request<ToolTelemetry>("/telemetry", signal),
    request<{ executions: ToolExecution[]; count: number }>("/executions?limit=12", signal),
    request<{ approvals: ToolApproval[]; count: number }>("/approvals?limit=8", signal),
    request<{ tools: ToolHealth[]; count: number }>("/health", signal),
    request<ToolManagerData["permissions"]>("/permissions", signal),
  ]);

  return {
    tools: tools.tools,
    telemetry,
    executions: executions.executions,
    approvals: approvals.approvals,
    health: health.tools,
    permissions,
  };
}
