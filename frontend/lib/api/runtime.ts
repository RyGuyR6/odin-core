export type RuntimeData = {
  runtime: {
    status: "healthy" | "degraded" | "offline";
    version: string;
    environment: string;
    started_at?: string | null;
    uptime_seconds: number;
    checked_at?: string;
    metrics: { cpu_percent: number; memory_percent: number; disk_percent: number };
  };
  agents: Array<{
    id: string;
    name: string;
    status: "offline" | "starting" | "idle" | "running" | "waiting_approval" | "succeeded" | "failed";
    description: string;
  }>;
  tasks: { queued: number; running: number; completed: number; failed: number };
  repositories: { connected: number };
  recent_activity: Array<{ id: string; timestamp: string; level: string; message: string }>;
  proxy?: { latencyMs: number; checkedAt: string };
};

export async function getRuntime(signal?: AbortSignal): Promise<RuntimeData> {
  const response = await fetch("/api/odin/runtime", { cache: "no-store", signal });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail ?? `Runtime request failed (${response.status})`);
  return body as RuntimeData;
}
