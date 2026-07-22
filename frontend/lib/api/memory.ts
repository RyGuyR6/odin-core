import { odinFetch } from "@/lib/api";

export type MemoryKind =
  | "note"
  | "document"
  | "code"
  | "conversation"
  | "decision"
  | "fact"
  | "summary"
  | "architecture_decision"
  | "repository_discovery"
  | "milestone_history"
  | "bug_investigation"
  | "fix_resolution"
  | "user_preference"
  | "engineering_note"
  | "coding_pattern"
  | "documentation_insight"
  | "test_strategy"
  | "project_history"
  | "ai_reasoning";

export type MemoryScope = "conversation" | "project" | "global";

export interface MemoryRecord {
  id: string;
  title: string | null;
  content: string;
  kind: MemoryKind;
  scope: MemoryScope;
  project_id: string | null;
  repository_id: string | null;
  conversation_id: string | null;
  source: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
  content_hash: string;
  version: number;
  importance: number;
  confidence: number;
  access_count: number;
  accessed_at: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  memory_id: string;
  chunk_id: string;
  title: string | null;
  content: string;
  kind: MemoryKind;
  scope: MemoryScope;
  project_id: string | null;
  repository_id: string | null;
  source: string | null;
  tags: string[];
  score: number;
  semantic_score: number;
  keyword_score: number;
  importance: number;
  metadata: Record<string, unknown>;
}

export interface KnowledgeEdge {
  id: string;
  source_memory_id: string;
  target_memory_id: string;
  relation: string;
  weight: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MemoryTelemetry {
  memories: number;
  chunks: number;
  edges: number;
  embedding_cache_entries: number;
  searches: number;
  semantic_searches: number;
  keyword_searches: number;
  hybrid_searches: number;
  cache_hits: number;
  cache_misses: number;
  average_search_ms: number;
  database_bytes: number;
  by_kind: Record<string, number>;
  by_scope: Record<string, number>;
}

export interface MemorySearchRequest {
  query: string;
  mode?: "semantic" | "keyword" | "hybrid";
  limit?: number;
  min_score?: number;
  scope?: MemoryScope;
  project_id?: string;
  repository_id?: string;
  conversation_id?: string;
  kinds?: MemoryKind[];
  tags?: string[];
}

export async function listMemories(params?: {
  limit?: number;
  offset?: number;
  scope?: MemoryScope;
  project_id?: string;
  repository_id?: string;
  kind?: MemoryKind;
}): Promise<MemoryRecord[]> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  if (params?.scope) query.set("scope", params.scope);
  if (params?.project_id) query.set("project_id", params.project_id);
  if (params?.repository_id) query.set("repository_id", params.repository_id);
  if (params?.kind) query.set("kind", params.kind);
  const qs = query.toString();
  return odinFetch<MemoryRecord[]>(`/memory${qs ? `?${qs}` : ""}`);
}

export async function getMemory(id: string): Promise<MemoryRecord> {
  return odinFetch<MemoryRecord>(`/memory/${id}`);
}

export async function searchMemory(
  request: MemorySearchRequest,
): Promise<SearchResult[]> {
  return odinFetch<SearchResult[]>("/memory/search", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function deleteMemory(id: string): Promise<void> {
  await odinFetch<void>(`/memory/${id}`, { method: "DELETE" });
}

export async function getMemoryTelemetry(): Promise<MemoryTelemetry> {
  return odinFetch<MemoryTelemetry>("/memory/telemetry");
}

export async function getMemoryGraph(
  memoryId?: string,
): Promise<KnowledgeEdge[]> {
  const qs = memoryId ? `?memory_id=${encodeURIComponent(memoryId)}` : "";
  return odinFetch<KnowledgeEdge[]>(`/memory/graph${qs}`);
}

export const KIND_LABELS: Record<MemoryKind, string> = {
  note: "Note",
  document: "Document",
  code: "Code",
  conversation: "Conversation",
  decision: "Decision",
  fact: "Fact",
  summary: "Summary",
  architecture_decision: "Architecture",
  repository_discovery: "Repository",
  milestone_history: "Milestone",
  bug_investigation: "Bug",
  fix_resolution: "Fix",
  user_preference: "Preference",
  engineering_note: "Engineering Note",
  coding_pattern: "Pattern",
  documentation_insight: "Docs",
  test_strategy: "Test Strategy",
  project_history: "History",
  ai_reasoning: "AI Reasoning",
};
