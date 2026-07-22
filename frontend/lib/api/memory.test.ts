import { describe, it, expect, vi, beforeEach } from "vitest";
import { listMemories, searchMemory, getMemoryTelemetry, KIND_LABELS } from "@/lib/api/memory";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

function mockResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  } as unknown as Response);
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe("memory API client", () => {
  it("listMemories sends correct request", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse([]));
    await listMemories({ limit: 10, kind: "architecture_decision" });
    const url: string = mockFetch.mock.calls[0][0];
    expect(url).toContain("/memory");
    expect(url).toContain("limit=10");
    expect(url).toContain("kind=architecture_decision");
  });

  it("searchMemory sends POST with body", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse([]));
    await searchMemory({ query: "fastapi", mode: "hybrid", limit: 5 });
    const [, init] = mockFetch.mock.calls[0];
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.query).toBe("fastapi");
    expect(body.mode).toBe("hybrid");
  });

  it("getMemoryTelemetry parses response", async () => {
    const telemetry = {
      memories: 42,
      chunks: 100,
      edges: 5,
      embedding_cache_entries: 20,
      searches: 200,
      semantic_searches: 80,
      keyword_searches: 60,
      hybrid_searches: 60,
      cache_hits: 180,
      cache_misses: 20,
      average_search_ms: 12.5,
      database_bytes: 1024000,
      by_kind: { note: 10, architecture_decision: 5 },
      by_scope: { global: 30, project: 12 },
    };
    mockFetch.mockResolvedValueOnce(mockResponse(telemetry));
    const result = await getMemoryTelemetry();
    expect(result.memories).toBe(42);
    expect(result.by_kind["architecture_decision"]).toBe(5);
    expect(result.by_scope["global"]).toBe(30);
  });

  it("KIND_LABELS covers all expected engineering kinds", () => {
    const engineeringKinds = [
      "architecture_decision",
      "repository_discovery",
      "milestone_history",
      "bug_investigation",
      "fix_resolution",
      "engineering_note",
      "coding_pattern",
      "test_strategy",
      "project_history",
      "ai_reasoning",
    ] as const;
    for (const kind of engineeringKinds) {
      expect(KIND_LABELS[kind]).toBeTruthy();
    }
  });

  it("listMemories with repository_id filter", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse([]));
    await listMemories({ repository_id: "repo-abc" });
    const url: string = mockFetch.mock.calls[0][0];
    expect(url).toContain("repository_id=repo-abc");
  });
});
