"use client";

import { FormEvent, useState } from "react";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "Odin is online. What should we build?",
    },
  ]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const message = input.trim();
    if (!message || sending) return;

    setInput("");
    setError("");
    setSending(true);
    setMessages((current) => [...current, { role: "user", content: message }]);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, conversationId }),
      });

      const body = (await response.json()) as {
        conversationId?: string;
        reply?: string;
        detail?: string;
      };

      if (!response.ok) {
        throw new Error(body.detail ?? "Odin could not answer.");
      }

      setConversationId(body.conversationId ?? conversationId);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: body.reply ?? "Odin returned an empty response.",
        },
      ]);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The request failed.",
      );
    } finally {
      setSending(false);
    }
  }

  function startNewConversation() {
    setConversationId(null);
    setMessages([
      {
        role: "assistant",
        content: "New conversation started. What should we build?",
      },
    ]);
    setError("");
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-8 sm:px-6">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.22em] text-zinc-500">
            OW-007 · Native AI Chat
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">
            Talk to Odin
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            odin-web → odin-api → Odin conversation runtime
          </p>
        </div>

        <button
          type="button"
          onClick={startNewConversation}
          className="rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          New chat
        </button>
      </header>

      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              className={
                message.role === "user"
                  ? "ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-zinc-900 px-4 py-3 text-sm leading-6 text-white dark:bg-zinc-100 dark:text-zinc-950"
                  : "mr-auto max-w-[85%] rounded-2xl rounded-bl-md bg-zinc-100 px-4 py-3 text-sm leading-6 text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100"
              }
            >
              {message.content}
            </div>
          ))}

          {sending && (
            <div className="mr-auto rounded-2xl rounded-bl-md bg-zinc-100 px-4 py-3 text-sm text-zinc-500 dark:bg-zinc-900">
              Odin is thinking…
            </div>
          )}
        </div>

        <form
          onSubmit={sendMessage}
          className="border-t border-zinc-200 p-4 dark:border-zinc-800"
        >
          {error && (
            <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}

          <div className="flex gap-3">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Ask Odin to create, inspect, plan, or explain…"
              rows={2}
              className="min-h-14 flex-1 resize-none rounded-xl border border-zinc-300 bg-transparent px-4 py-3 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700"
            />

            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="rounded-xl bg-zinc-900 px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-950"
            >
              Send
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
