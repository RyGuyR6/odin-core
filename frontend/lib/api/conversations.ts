import type {
  ConversationRecord,
  MessageRecord,
  ConversationCreate,
  ConversationUpdate,
} from "./types";

const BASE = "/api/conversations";

async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
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

export async function listConversations(): Promise<ConversationRecord[]> {
  return apiFetch<ConversationRecord[]>("?limit=100");
}

export async function createConversation(
  data: ConversationCreate,
): Promise<ConversationRecord> {
  return apiFetch<ConversationRecord>("", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getConversation(id: string): Promise<ConversationRecord> {
  return apiFetch<ConversationRecord>(`/${id}`);
}

export async function updateConversation(
  id: string,
  data: ConversationUpdate,
): Promise<ConversationRecord> {
  return apiFetch<ConversationRecord>(`/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteConversation(id: string): Promise<void> {
  return apiFetch<void>(`/${id}`, { method: "DELETE" });
}

export async function restoreConversation(
  id: string,
): Promise<ConversationRecord> {
  return apiFetch<ConversationRecord>(`/${id}/restore`, { method: "POST" });
}

export async function listMessages(id: string): Promise<MessageRecord[]> {
  return apiFetch<MessageRecord[]>(`/${id}/messages`);
}

export async function searchConversations(
  query: string,
): Promise<SearchResult[]> {
  return apiFetch<SearchResult[]>("/search", {
    method: "POST",
    body: JSON.stringify({ query, limit: 30 }),
  });
}

export async function autoTitle(id: string): Promise<{ title: string }> {
  return apiFetch<{ title: string }>(`/${id}/auto-title`, { method: "POST" });
}

export interface SearchResult {
  conversation_id: string;
  title: string;
  message_id: string;
  role: string;
  content: string;
  created_at: string;
}
