"use client";

import { useEffect, useRef, KeyboardEvent } from "react";
import { Send, Square } from "lucide-react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  onStop,
  isStreaming,
  disabled,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isStreaming && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isStreaming]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming && value.trim() && !disabled) {
        onSubmit();
      }
    }
    if (e.key === "Escape" && isStreaming) {
      onStop();
    }
  }

  return (
    <div className="flex gap-3">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={
          isStreaming ? "Odin is thinking…" : "Ask Odin to create, inspect, plan, or explain… (⌘↵ to send)"
        }
        disabled={isStreaming || disabled}
        rows={1}
        className="min-h-[44px] flex-1 resize-none rounded-xl border border-zinc-700 bg-transparent px-4 py-3 text-sm outline-none transition focus:border-violet-500 disabled:text-zinc-500 dark:border-zinc-700"
        style={{ maxHeight: "200px", overflowY: "auto" }}
      />

      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          title="Stop generation (Esc)"
          className="flex h-11 w-11 items-center justify-center rounded-xl border border-zinc-600 text-zinc-400 transition hover:border-red-500 hover:text-red-400"
        >
          <Square size={16} />
        </button>
      ) : (
        <button
          type="button"
          onClick={onSubmit}
          disabled={!value.trim() || disabled}
          title="Send (Enter)"
          className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-600 text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send size={16} />
        </button>
      )}
    </div>
  );
}
