"use client";

import { useState, useMemo } from "react";
import { Plus, Search, Archive, Trash2, Edit2, Check, X, MoreHorizontal } from "lucide-react";
import type { ConversationRecord } from "@/lib/api/types";

interface ConversationSidebarProps {
  conversations: ConversationRecord[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onRename: (id: string, title: string) => Promise<void>;
  onArchive: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  loading?: boolean;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function ConversationItem({
  conversation,
  active,
  onSelect,
  onRename,
  onArchive,
  onDelete,
}: {
  conversation: ConversationRecord;
  active: boolean;
  onSelect: () => void;
  onRename: (title: string) => Promise<void>;
  onArchive: () => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(conversation.title);
  const [menuOpen, setMenuOpen] = useState(false);

  async function submitRename() {
    if (renameValue.trim() && renameValue !== conversation.title) {
      await onRename(renameValue.trim());
    }
    setRenaming(false);
    setMenuOpen(false);
  }

  return (
    <div
      className={`group relative flex cursor-pointer items-start gap-2 rounded-lg px-3 py-2.5 transition ${
        active
          ? "bg-violet-600/20 text-violet-100"
          : "text-zinc-400 hover:bg-[var(--surface-2)] hover:text-white"
      }`}
      onClick={() => {
        if (!renaming) onSelect();
      }}
    >
      {renaming ? (
        <div className="flex flex-1 items-center gap-1.5">
          <input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submitRename();
              if (e.key === "Escape") setRenaming(false);
            }}
            className="flex-1 rounded bg-zinc-800 px-2 py-1 text-sm text-white outline-none"
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={(e) => { e.stopPropagation(); void submitRename(); }}
            className="rounded p-1 hover:text-violet-400"
          >
            <Check size={13} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setRenaming(false); }}
            className="rounded p-1 hover:text-red-400"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{conversation.title}</p>
            <p className="mt-0.5 text-[11px] text-zinc-500">
              {timeAgo(conversation.updated_at)}
              {conversation.message_count > 0 && (
                <> · {conversation.message_count} msgs</>
              )}
            </p>
          </div>

          <div className="relative">
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
              className={`rounded p-1 transition ${
                menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100"
              } hover:bg-zinc-700`}
            >
              <MoreHorizontal size={14} />
            </button>

            {menuOpen && (
              <div
                className="absolute right-0 top-6 z-50 min-w-[130px] rounded-xl border border-zinc-700 bg-zinc-900 py-1 shadow-xl"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => { setRenaming(true); setMenuOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white"
                >
                  <Edit2 size={13} /> Rename
                </button>
                <button
                  onClick={() => { void onArchive(); setMenuOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white"
                >
                  <Archive size={13} /> Archive
                </button>
                <button
                  onClick={() => { void onDelete(); setMenuOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-zinc-800 hover:text-red-300"
                >
                  <Trash2 size={13} /> Delete
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onRename,
  onArchive,
  onDelete,
  loading,
}: ConversationSidebarProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations.filter((c) => !c.archived);
    return conversations.filter(
      (c) => !c.archived && c.title.toLowerCase().includes(q),
    );
  }, [conversations, query]);

  return (
    <div className="flex h-full flex-col gap-3">
      {/* New Chat button */}
      <button
        onClick={onNewChat}
        className="flex items-center gap-2 rounded-xl border border-violet-600 bg-violet-600/10 px-3 py-2.5 text-sm font-medium text-violet-300 transition hover:bg-violet-600/20"
      >
        <Plus size={16} />
        New Chat
      </button>

      {/* Search */}
      <div className="relative">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search conversations…"
          className="w-full rounded-lg border border-zinc-700 bg-transparent py-2 pl-8 pr-3 text-sm outline-none placeholder:text-zinc-600 focus:border-zinc-500"
        />
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto space-y-1 pr-0.5" role="list" aria-label="Conversations">
        {loading && (
          <div className="space-y-2 pt-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-12 animate-pulse rounded-lg bg-zinc-800"
              />
            ))}
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <p className="px-3 py-4 text-center text-xs text-zinc-600">
            {query ? "No conversations match your search." : "No conversations yet."}
          </p>
        )}

        {filtered.map((conv) => (
          <ConversationItem
            key={conv.id}
            conversation={conv}
            active={conv.id === activeId}
            onSelect={() => onSelect(conv.id)}
            onRename={(title) => onRename(conv.id, title)}
            onArchive={() => onArchive(conv.id)}
            onDelete={() => onDelete(conv.id)}
          />
        ))}
      </div>
    </div>
  );
}
