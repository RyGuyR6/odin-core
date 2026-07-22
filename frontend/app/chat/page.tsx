"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, MessageSquare, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type { ConversationRecord, MessageRecord } from "@/lib/api/types";
import {
  createConversation,
  listConversations,
  listMessages,
  updateConversation,
  deleteConversation,
} from "@/lib/api/conversations";
import { ConversationSidebar } from "@/components/chat/conversation-sidebar";
import { MessageBubble, StreamingBubble } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [input, setInput] = useState("");
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load conversation list
  const refreshConversations = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations(list);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void refreshConversations();
    }, 0);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Scroll to bottom whenever messages/streaming changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  async function selectConversation(id: string) {
    setActiveId(id);
    setError("");
    setLoadingMessages(true);
    try {
      const msgs = await listMessages(id);
      setMessages(msgs);
    } catch {
      setError("Could not load messages.");
    } finally {
      setLoadingMessages(false);
    }
  }

  async function startNewChat() {
    setActiveId(null);
    setMessages([]);
    setInput("");
    setError("");
    setStreamingContent(null);
  }

  async function sendMessage(content: string = input.trim()) {
    if (!content || streamingContent !== null) return;

    setInput("");
    setError("");

    let conversationId = activeId;

    // Create conversation if needed
    if (!conversationId) {
      try {
        const conv = await createConversation({
          title: content.slice(0, 80),
          metadata: { source: "odin-web-ow007" },
        });
        conversationId = conv.id;
        setActiveId(conv.id);
        await refreshConversations();
      } catch {
        setError("Could not create conversation.");
        return;
      }
    }

    // Optimistic user message
    const optimisticUser: MessageRecord = {
      id: `optimistic-${Date.now()}`,
      conversation_id: conversationId,
      role: "user",
      content,
      name: null,
      tool_call_id: null,
      metadata: {},
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      provider: null,
      model: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    setStreamingContent("");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(
        `/api/conversations/${conversationId}/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        },
      );

      if (!response.ok || !response.body) {
        throw new Error(`Server error ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const parsed = JSON.parse(line.slice(6)) as {
              delta?: string;
              done?: boolean;
              error?: string;
            };

            if (parsed.error) {
              throw new Error(parsed.error);
            }
            if (parsed.delta) {
              accumulated += parsed.delta;
              setStreamingContent(accumulated);
            }
            if (parsed.done) {
              break;
            }
          } catch (parseErr) {
            // Silently skip unparseable SSE lines; rethrow real errors
            if (!(parseErr instanceof SyntaxError)) {
              throw parseErr;
            }
          }
        }
      }

      // Reload messages from backend to get persisted IDs and token counts
      const freshMessages = await listMessages(conversationId);
      setMessages(freshMessages);
      await refreshConversations();
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        // Stopped by user — reload persisted messages
        if (conversationId) {
          const freshMessages = await listMessages(conversationId).catch(() => messages);
          setMessages(freshMessages);
        }
      } else {
        setError(
          e instanceof Error ? e.message : "Something went wrong. Please try again.",
        );
        // Remove optimistic message on hard error
        setMessages((prev) =>
          prev.filter((m) => m.id !== optimisticUser.id),
        );
      }
    } finally {
      setStreamingContent(null);
      abortRef.current = null;
    }
  }

  function stopGeneration() {
    abortRef.current?.abort();
  }

  async function handleRegenerate() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    // Remove last assistant message optimistically
    setMessages((prev) => {
      const idx = [...prev].reverse().findIndex((m) => m.role === "assistant");
      if (idx === -1) return prev;
      const realIdx = prev.length - 1 - idx;
      return prev.slice(0, realIdx);
    });
    await sendMessage(lastUser.content);
  }

  async function handleEdit(content: string) {
    await sendMessage(content);
  }

  async function handleRename(id: string, title: string) {
    await updateConversation(id, { title });
    await refreshConversations();
  }

  async function handleArchive(id: string) {
    await updateConversation(id, { archived: true });
    if (activeId === id) await startNewChat();
    await refreshConversations();
  }

  async function handleDelete(id: string) {
    await deleteConversation(id);
    if (activeId === id) await startNewChat();
    await refreshConversations();
  }

  const isStreaming = streamingContent !== null;

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`flex-shrink-0 border-r border-[var(--border)] bg-[rgba(8,11,18,0.82)] p-4 transition-all duration-200 ${
          sidebarOpen ? "w-64" : "w-0 overflow-hidden p-0"
        }`}
      >
        {sidebarOpen && (
          <ConversationSidebar
            conversations={conversations}
            activeId={activeId}
            onSelect={selectConversation}
            onNewChat={startNewChat}
            onRename={handleRename}
            onArchive={handleArchive}
            onDelete={handleDelete}
            loading={loading}
          />
        )}
      </aside>

      {/* Main panel */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Toolbar */}
        <div className="flex items-center gap-3 border-b border-[var(--border)] bg-[rgba(8,11,18,0.6)] px-4 py-3">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            className="rounded-lg border border-[var(--border)] p-2 text-zinc-400 transition hover:bg-[var(--surface-2)] hover:text-white"
          >
            {sidebarOpen ? (
              <PanelLeftClose size={16} />
            ) : (
              <PanelLeftOpen size={16} />
            )}
          </button>

          <div className="flex items-center gap-2">
            <Bot size={18} className="text-violet-400" />
            <span className="text-sm font-medium text-zinc-200">
              {activeId
                ? (conversations.find((c) => c.id === activeId)?.title ?? "Chat")
                : "Odin Chat"}
            </span>
          </div>

          {activeId && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-zinc-600">
                {conversations.find((c) => c.id === activeId)?.message_count ?? 0} messages
              </span>
            </div>
          )}
        </div>

        {/* Message list */}
        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          {!activeId && !isStreaming && messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="grid h-16 w-16 place-items-center rounded-2xl bg-violet-600/10 text-violet-400">
                <MessageSquare size={32} />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-zinc-200">
                  Start a conversation
                </h2>
                <p className="mt-1 text-sm text-zinc-500">
                  Ask Odin to create, inspect, plan, or explain anything.
                </p>
              </div>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {[
                  "Explain the repository architecture",
                  "What tasks are currently running?",
                  "Review the latest changes",
                  "Help me write a unit test",
                ].map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => {
                      setInput(prompt);
                    }}
                    className="rounded-xl border border-zinc-700 px-4 py-3 text-left text-sm text-zinc-400 transition hover:border-zinc-500 hover:text-white"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4">
              {loadingMessages ? (
                <div className="space-y-4">
                  {[1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}
                    >
                      <div className="h-12 w-64 animate-pulse rounded-2xl bg-zinc-800" />
                    </div>
                  ))}
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <MessageBubble
                    key={msg.id}
                    message={msg}
                    onRegenerate={
                      idx === messages.length - 1 && msg.role === "assistant"
                        ? handleRegenerate
                        : undefined
                    }
                    onEdit={
                      msg.role === "user"
                        ? handleEdit
                        : undefined
                    }
                  />
                ))
              )}

              {isStreaming && (
                <StreamingBubble content={streamingContent ?? ""} />
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="border-t border-[var(--border)] bg-[rgba(8,11,18,0.6)] px-4 py-4 sm:px-8">
          <div className="mx-auto max-w-3xl">
            {error && (
              <div className="mb-3 rounded-xl border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-300">
                {error}
              </div>
            )}
            <ChatInput
              value={input}
              onChange={setInput}
              onSubmit={() => void sendMessage()}
              onStop={stopGeneration}
              isStreaming={isStreaming}
            />
            <p className="mt-2 text-center text-[11px] text-zinc-600">
              Enter to send · Shift+Enter for newline · Esc to stop generation
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
