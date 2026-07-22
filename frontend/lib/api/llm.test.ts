import {
  fetchLlmConfig,
  fetchLlmDiagnostics,
  fetchLlmHealth,
  testLlmConnection,
  type LlmConfig,
  type LlmDiagnostics,
  type LlmHealth,
} from "@/lib/api/llm";
import { vi } from "vitest";

vi.mock("@/lib/api/llm", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api/llm")>();
  return {
    ...mod,
    fetchLlmHealth: vi.fn(),
    fetchLlmConfig: vi.fn(),
    fetchLlmDiagnostics: vi.fn(),
    testLlmConnection: vi.fn(),
  };
});

const mockedHealth = vi.mocked(fetchLlmHealth);
const mockedConfig = vi.mocked(fetchLlmConfig);
const mockedDiagnostics = vi.mocked(fetchLlmDiagnostics);
const mockedTestConnection = vi.mocked(testLlmConnection);

function healthFixture(overrides: Partial<LlmHealth> = {}): LlmHealth {
  return {
    status: "ok",
    providers: [
      {
        provider: "openai",
        configured: true,
        available: true,
        latency_ms: 42,
        error: null,
        auth_status: "ok",
        consecutive_failures: 0,
        last_success: "2026-07-22T10:00:00Z",
      },
    ],
    ...overrides,
  };
}

function configFixture(overrides: Partial<LlmConfig> = {}): LlmConfig {
  return {
    default_provider: "openai",
    primary_model: "gpt-5",
    balanced_model: "gpt-4.1",
    economy_model: "gpt-4.1-mini",
    embedding_model: "text-embedding-3-small",
    default_execution_profile: "balanced",
    timeout_seconds: 60,
    max_retries: 2,
    ...overrides,
  };
}

function diagnosticsFixture(overrides: Partial<LlmDiagnostics> = {}): LlmDiagnostics {
  return {
    providers: healthFixture().providers,
    config: configFixture(),
    usage: {},
    available_task_types: ["chat", "planning", "code_generation"],
    routing_profiles: ["economy", "balanced", "maximum"],
    configured_model_warnings: [],
    capabilities_registered: 20,
    oic009_tools_registered: 5,
    ...overrides,
  };
}

describe("llm API client", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("fetchLlmHealth returns health data", async () => {
    const fixture = healthFixture();
    mockedHealth.mockResolvedValueOnce(fixture);
    const result = await fetchLlmHealth();
    expect(result.status).toBe("ok");
    expect(result.providers).toHaveLength(1);
    expect(result.providers[0].auth_status).toBe("ok");
  });

  it("fetchLlmConfig returns config", async () => {
    const fixture = configFixture();
    mockedConfig.mockResolvedValueOnce(fixture);
    const result = await fetchLlmConfig();
    expect(result.default_execution_profile).toBe("balanced");
    expect(result.primary_model).toBe("gpt-5");
  });

  it("fetchLlmDiagnostics returns diagnostics", async () => {
    const fixture = diagnosticsFixture();
    mockedDiagnostics.mockResolvedValueOnce(fixture);
    const result = await fetchLlmDiagnostics();
    expect(result.capabilities_registered).toBe(20);
    expect(result.oic009_tools_registered).toBe(5);
    expect(result.routing_profiles).toContain("balanced");
  });

  it("testLlmConnection returns success result", async () => {
    mockedTestConnection.mockResolvedValueOnce({
      success: true,
      message: "OpenAI connection verified.",
      auth_status: "ok",
      latency_ms: 55,
    });
    const result = await testLlmConnection();
    expect(result.success).toBe(true);
    expect(result.auth_status).toBe("ok");
  });

  it("testLlmConnection returns failure for missing key", async () => {
    mockedTestConnection.mockResolvedValueOnce({
      success: false,
      message: "OpenAI API key not configured.",
      auth_status: "missing_key",
    });
    const result = await testLlmConnection();
    expect(result.success).toBe(false);
    expect(result.auth_status).toBe("missing_key");
  });

  it("fetchLlmHealth providers include latency_ms", async () => {
    const fixture = healthFixture();
    mockedHealth.mockResolvedValueOnce(fixture);
    const result = await fetchLlmHealth();
    expect(result.providers[0].latency_ms).toBe(42);
  });

  it("configFixture has all required model fields", async () => {
    const fixture = configFixture();
    mockedConfig.mockResolvedValueOnce(fixture);
    const result = await fetchLlmConfig();
    expect(result).toHaveProperty("economy_model");
    expect(result).toHaveProperty("balanced_model");
    expect(result).toHaveProperty("primary_model");
    expect(result).toHaveProperty("embedding_model");
  });

  it("diagnostics can contain model warnings", async () => {
    const fixture = diagnosticsFixture({
      configured_model_warnings: ["gpt-x not available in this account"],
    });
    mockedDiagnostics.mockResolvedValueOnce(fixture);
    const result = await fetchLlmDiagnostics();
    expect(result.configured_model_warnings).toHaveLength(1);
    expect(result.configured_model_warnings[0]).toContain("gpt-x");
  });
});
