const BASE = "/api/llm";

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `API error ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export interface ModelCapabilities {
  supports_streaming: boolean;
  supports_tools: boolean;
  supports_json: boolean;
  supports_reasoning: boolean;
  supports_embeddings: boolean;
  supports_vision: boolean;
  context_window: number;
  max_output_tokens: number | null;
}

export interface ModelInfo {
  id: string;
  provider: string;
  description: string;
  capabilities: ModelCapabilities;
  supports_streaming: boolean;
  supports_tools: boolean;
  supports_json: boolean;
  supports_reasoning: boolean;
  supports_embeddings: boolean;
  available: boolean;
  availability_verified: boolean;
}

export interface ProviderHealth {
  provider: string;
  configured: boolean;
  available: boolean;
  latency_ms: number | null;
  error: string | null;
  auth_status: "ok" | "missing_key" | "invalid_key" | "unknown";
  consecutive_failures: number;
  last_success: string | null;
}

export interface LlmHealth {
  status: string;
  providers: ProviderHealth[];
}

export interface LlmConfig {
  default_provider: string;
  primary_model: string;
  balanced_model: string;
  economy_model: string;
  embedding_model: string;
  default_execution_profile: string;
  timeout_seconds: number;
  max_retries: number;
}

export interface ConfiguredModelStatus {
  primary_model?: boolean;
  balanced_model?: boolean;
  economy_model?: boolean;
  embedding_model?: boolean;
  note?: string;
}

export interface LlmTestConnectionResult {
  success: boolean;
  message: string;
  auth_status: "ok" | "missing_key" | "invalid_key" | "unknown";
  latency_ms?: number;
  configured_model_status?: ConfiguredModelStatus;
}

export interface LlmDiagnostics {
  providers: ProviderHealth[];
  config: LlmConfig;
  usage: Record<string, unknown>;
  available_task_types: string[];
  routing_profiles: string[];
  configured_model_warnings: string[];
  capabilities_registered: number;
  oic009_tools_registered: number;
}

export async function fetchLlmHealth(): Promise<LlmHealth> {
  return apiFetch<LlmHealth>("/health");
}

export async function fetchLlmProviders(): Promise<ProviderHealth[]> {
  return apiFetch<ProviderHealth[]>("/providers");
}

export async function fetchLlmModels(): Promise<ModelInfo[]> {
  return apiFetch<ModelInfo[]>("/models");
}

export async function fetchLlmCapabilities(): Promise<
  Record<string, ModelCapabilities>
> {
  return apiFetch<Record<string, ModelCapabilities>>("/capabilities");
}

export async function fetchLlmConfig(): Promise<LlmConfig> {
  return apiFetch<LlmConfig>("/config");
}

export async function fetchLlmDiagnostics(): Promise<LlmDiagnostics> {
  return apiFetch<LlmDiagnostics>("/diagnostics");
}

export async function testLlmConnection(): Promise<LlmTestConnectionResult> {
  return apiFetch<LlmTestConnectionResult>("/test-connection", {
    method: "POST",
  });
}
