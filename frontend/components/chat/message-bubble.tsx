"use client";

import { useState } from "react";
import { Check, Copy, RotateCcw, Edit2 } from "lucide-react";
import type { MessageRecord } from "@/lib/api/types";
import { MarkdownContent } from "./markdown-content";

interface MessageBubbleProps {
  message: MessageRecord;
  isStreaming?: boolean;
  onRegenerate?: () => void;
  onEdit?: (content: string) => void;
}

export function MessageBubble({
  message,
  isStreaming,
  onRegenerate,
  onEdit,
}: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(message.content);

  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  function copyMessage() {
    void navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function submitEdit() {
    if (editValue.trim() && onEdit) {
      onEdit(editValue.trim());
    }
    setEditing(false);
  }

  const totalTokens =
    (message.prompt_tokens ?? 0) + (message.completion_tokens ?? 0);

  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`relative max-w-[85%] ${
          isUser
            ? "rounded-2xl rounded-br-md bg-zinc-900 px-4 py-3 text-sm text-white dark:bg-zinc-100 dark:text-zinc-950"
            : "rounded-2xl rounded-bl-md px-4 py-3 text-sm text-zinc-900 dark:text-zinc-100"
        }`}
      >
        {/* Edit mode for user messages */}
        {isUser && editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submitEdit();
                }
                if (e.key === "Escape") setEditing(false);
              }}
              className="min-h-[60px] w-full resize-none rounded-lg border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-white outline-none focus:border-zinc-400 dark:bg-zinc-200 dark:text-zinc-950"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                onClick={submitEdit}
                className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500"
              >
                Send
              </button>
              <button
                onClick={() => setEditing(false)}
                className="rounded-lg border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-400"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : isAssistant ? (
          <div className="prose-sm max-w-none">
            <MarkdownContent content={message.content} />
            {isStreaming && (
              <span className="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-violet-400" />
            )}
          </div>
        ) : (
          <p className="whitespace-pre-wrap leading-6">{message.content}</p>
        )}

        {/* Action toolbar */}
        {!editing && (
          <div
            className={`mt-1.5 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100 ${
              isUser ? "justify-end" : "justify-start"
            }`}
          >
            {/* Token usage badge */}
            {isAssistant && totalTokens > 0 && (
              <span className="text-[10px] text-zinc-400">
                {totalTokens.toLocaleString()} tokens
                {message.model && (
                  <> · {message.model.split("/").pop()}</>
                )}
              </span>
            )}

            <button
              onClick={copyMessage}
              title="Copy message"
              className="rounded p-1 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </button>

            {isUser && onEdit && (
              <button
                onClick={() => {
                  setEditValue(message.content);
                  setEditing(true);
                }}
                title="Edit and resend"
                className="rounded p-1 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
              >
                <Edit2 size={13} />
              </button>
            )}

            {isAssistant && onRegenerate && !isStreaming && (
              <button
                onClick={onRegenerate}
                title="Regenerate"
                className="rounded p-1 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
              >
                <RotateCcw size={13} />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 text-sm text-zinc-900 dark:text-zinc-100">
        {content ? (
          <div className="prose-sm max-w-none">
            <MarkdownContent content={content} />
            <span className="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-violet-400" />
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-zinc-400">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:0ms]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:150ms]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:300ms]" />
          </div>
        )}
      </div>
    </div>
  );
}
