const BASE = "/api/ai/operations";

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `API error ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export interface OperationsOverview {
  total_requests: number;
  successes: number;
  failures: number;
  failure_rate: number;
  average_latency_ms: number;
  total_tokens: number;
  total_estimated_cost_usd: number;
  execution_profile_usage: Record<string, number>;
  provider_distribution: Record<string, number>;
}

export interface OperationEvent {
  request_id: string;
  timestamp: string;
  provider: string;
  model: string;
  task_type: string | null;
  execution_profile: string | null;
  latency_ms: number;
  estimated_cost_usd: number;
  total_tokens: number;
  status: "success" | "failure";
}

export interface ProviderOperationsHealth {
  provider: string;
  available: boolean;
  auth_status: string;
  average_latency_ms: number;
  failure_rate: number;
  configured_models: string[];
  available_models: string[];
}

export async function fetchOperationsOverview(): Promise<OperationsOverview> {
  return apiFetch<OperationsOverview>("/overview");
}

export async function fetchOperationsHistory(
  limit = 10,
): Promise<OperationEvent[]> {
  return apiFetch<OperationEvent[]>(`/history?limit=${limit}`);
}

export async function fetchOperationsProviders(): Promise<
  ProviderOperationsHealth[]
> {
  return apiFetch<ProviderOperationsHealth[]>("/providers");
}
