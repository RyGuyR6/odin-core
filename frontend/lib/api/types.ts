export interface ConversationRecord {
  id: string;
  title: string;
  user_id: string | null;
  summary: string | null;
  metadata: Record<string, unknown>;
  archived: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface MessageRecord {
  id: string;
  conversation_id: string;
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  name: string | null;
  tool_call_id: string | null;
  metadata: Record<string, unknown>;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  provider: string | null;
  model: string | null;
  created_at: string;
}

export interface ConversationCreate {
  title?: string;
  user_id?: string;
  metadata?: Record<string, unknown>;
}

export interface ConversationUpdate {
  title?: string;
  archived?: boolean;
  metadata?: Record<string, unknown>;
}
