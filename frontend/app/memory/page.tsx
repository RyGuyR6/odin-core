"use client";

import { Brain, ChevronRight, Database, Hash, Search, TriangleAlert, X, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import {
  deleteMemory,
  getMemoryTelemetry,
  listMemories,
  searchMemory,
  KIND_LABELS,
  type MemoryKind,
  type MemoryRecord,
  type MemoryTelemetry,
  type SearchResult,
} from "@/lib/api/memory";

// ── Helpers ─────────────────────────────────────────────────────────────────

function kindBadgeClass(kind: MemoryKind): string {
  const engineering: MemoryKind[] = [
    "architecture_decision", "repository_discovery", "milestone_history",
    "bug_investigation", "fix_resolution", "engineering_note", "coding_pattern",
    "test_strategy", "project_history", "ai_reasoning",
  ];
  if (engineering.includes(kind)) return "border-violet-400/20 bg-violet-500/10 text-violet-200";
  if (kind === "conversation") return "border-sky-400/20 bg-sky-500/10 text-sky-200";
  if (kind === "decision" || kind === "user_preference") return "border-amber-400/20 bg-amber-400/10 text-amber-200";
  if (kind === "code") return "border-emerald-400/20 bg-emerald-500/10 text-emerald-200";
  return "border-zinc-400/20 bg-zinc-500/10 text-zinc-200";
}

function importanceDots(value: number) {
  const filled = Math.round(value * 5);
  return Array.from({ length: 5 }, (_, i) => (
    <span key={i} className={`inline-block h-1.5 w-1.5 rounded-full ${i < filled ? "bg-violet-400" : "bg-zinc-700"}`} />
  ));
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Sub-components ───────────────────────────────────────────────────────────

function StatCard({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Brain }) {
  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted)]">{label}</p>
        <Icon size={18} className="text-violet-200" />
      </div>
      <p className="mt-4 text-3xl font-semibold">{value}</p>
    </article>
  );
}

function MemoryCard({
  memory,
  selected,
  onSelect,
  onDelete,
}: {
  memory: MemoryRecord | SearchResult;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const id = "memory_id" in memory ? memory.memory_id : memory.id;
  const score = "score" in memory ? memory.score : null;

  return (
    <article
      onClick={onSelect}
      className={`cursor-pointer rounded-xl border p-4 transition ${
        selected
          ? "border-violet-500/40 bg-violet-500/5"
          : "border-[var(--border)] bg-black/10 hover:border-violet-500/20"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`rounded-full border px-2 py-0.5 text-xs ${kindBadgeClass(memory.kind)}`}>
              {KIND_LABELS[memory.kind] ?? memory.kind}
            </span>
            <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--muted)]">
              {memory.scope}
            </span>
            {score !== null && (
              <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--muted)]">
                {(score * 100).toFixed(0)}% match
              </span>
            )}
          </div>
          <p className="mt-2 font-medium leading-snug">
            {memory.title ?? <span className="text-[var(--muted)]">(no title)</span>}
          </p>
          <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">{memory.content}</p>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="rounded-lg border border-[var(--border)] p-1.5 text-[var(--muted)] opacity-0 transition hover:text-rose-300 group-hover:opacity-100"
          aria-label="Delete memory"
          title="Delete"
        >
          <X size={14} />
        </button>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <span className="flex items-center gap-0.5" title={`Importance: ${memory.importance}`}>
          {importanceDots(memory.importance)}
        </span>
        {memory.tags.slice(0, 4).map((tag) => (
          <span key={tag} className="text-xs text-[var(--muted)]">#{tag}</span>
        ))}
      </div>
    </article>
  );
}

function DetailPanel({ memory, onClose, onDelete }: {
  memory: MemoryRecord;
  onClose: () => void;
  onDelete: () => void;
}) {
  return (
    <aside className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 space-y-4 overflow-y-auto max-h-[calc(100vh-14rem)]">
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className={`rounded-full border px-2 py-0.5 text-xs ${kindBadgeClass(memory.kind)}`}>
            {KIND_LABELS[memory.kind] ?? memory.kind}
          </span>
          <h2 className="mt-2 font-semibold leading-snug">
            {memory.title ?? <span className="text-[var(--muted)]">(no title)</span>}
          </h2>
        </div>
        <button onClick={onClose} className="rounded-lg border border-[var(--border)] p-1.5" aria-label="Close">
          <X size={15} />
        </button>
      </div>

      <div className="text-sm text-[var(--muted)] space-y-1">
        <div className="flex gap-2"><span className="w-24 shrink-0">Scope</span><span className="text-white">{memory.scope}</span></div>
        <div className="flex gap-2"><span className="w-24 shrink-0">Importance</span><span className="text-white">{(memory.importance * 100).toFixed(0)}%</span></div>
        <div className="flex gap-2"><span className="w-24 shrink-0">Confidence</span><span className="text-white">{(memory.confidence * 100).toFixed(0)}%</span></div>
        <div className="flex gap-2"><span className="w-24 shrink-0">Access count</span><span className="text-white">{memory.access_count}</span></div>
        <div className="flex gap-2"><span className="w-24 shrink-0">Version</span><span className="text-white">{memory.version}</span></div>
        <div className="flex gap-2"><span className="w-24 shrink-0">Chunks</span><span className="text-white">{memory.chunk_count}</span></div>
        {memory.source && <div className="flex gap-2"><span className="w-24 shrink-0">Source</span><span className="text-white truncate">{memory.source}</span></div>}
        {memory.repository_id && <div className="flex gap-2"><span className="w-24 shrink-0">Repository</span><span className="text-white truncate">{memory.repository_id}</span></div>}
        <div className="flex gap-2"><span className="w-24 shrink-0">Created</span><span className="text-white">{new Date(memory.created_at).toLocaleString()}</span></div>
        <div className="flex gap-2"><span className="w-24 shrink-0">Updated</span><span className="text-white">{new Date(memory.updated_at).toLocaleString()}</span></div>
      </div>

      {memory.tags.length > 0 && (
        <div>
          <p className="text-xs text-[var(--muted)] mb-1">Tags</p>
          <div className="flex flex-wrap gap-1">
            {memory.tags.map((tag) => (
              <span key={tag} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs">#{tag}</span>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="text-xs text-[var(--muted)] mb-1">Content</p>
        <pre className="whitespace-pre-wrap text-sm text-zinc-300 rounded-lg border border-[var(--border)] bg-black/20 p-3 overflow-auto max-h-60">{memory.content}</pre>
      </div>

      <button
        onClick={onDelete}
        className="w-full rounded-lg border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-200 transition hover:bg-rose-500/20"
      >
        Delete memory
      </button>
    </aside>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function MemoryPage() {
  const [telemetry, setTelemetry] = useState<MemoryTelemetry | null>(null);
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [selected, setSelected] = useState<MemoryRecord | null>(null);
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<MemoryKind | "">("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const searchRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const [tel, mems] = await Promise.all([
        getMemoryTelemetry(),
        listMemories({ limit: 50, kind: kindFilter || undefined }),
      ]);
      setTelemetry(tel);
      setMemories(mems);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memory data");
    } finally {
      setLoading(false);
    }
  }, [kindFilter]);

  useEffect(() => { void load(); }, [load]);

  // Debounced semantic search
  useEffect(() => {
    if (searchRef.current) clearTimeout(searchRef.current);
    if (!query.trim()) { setSearchResults(null); return; }
    searchRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const results = await searchMemory({
          query: query.trim(),
          mode: "hybrid",
          limit: 20,
          min_score: 0.05,
          kinds: kindFilter ? [kindFilter] : undefined,
        });
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 400);
  }, [query, kindFilter]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await deleteMemory(id);
      if (selected?.id === id) setSelected(null);
      await load();
    } catch {
      // ignore
    }
  }, [selected, load]);

  const displayItems = searchResults ?? memories;
  const kindOptions = useMemo(() => Object.entries(KIND_LABELS), []);

  return (
    <div className="space-y-7">
      <PageHeader
        eyebrow="OIC-011"
        title="Memory Explorer"
        description="Persistent knowledge base — browse, search, and manage Odin's long-term memory."
      />

      {/* Stats */}
      {loading && !telemetry && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-2xl border border-[var(--border)] bg-[var(--surface)]" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-2xl border border-rose-400/20 bg-rose-400/5 p-6">
          <TriangleAlert className="text-rose-300" />
          <p className="mt-3 text-sm">{error}</p>
          <button onClick={() => void load()} className="mt-4 rounded-lg border border-[var(--border)] px-3 py-2 text-sm">
            Retry
          </button>
        </div>
      )}

      {telemetry && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Total memories" value={String(telemetry.memories)} icon={Brain} />
            <StatCard label="Knowledge chunks" value={String(telemetry.chunks)} icon={Hash} />
            <StatCard label="Graph edges" value={String(telemetry.edges)} icon={Zap} />
            <StatCard label="Storage" value={formatBytes(telemetry.database_bytes)} icon={Database} />
          </div>

          {/* Kind breakdown */}
          {Object.keys(telemetry.by_kind).length > 0 && (
            <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
              <h2 className="font-medium mb-3">Memory by kind</h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(telemetry.by_kind)
                  .sort((a, b) => b[1] - a[1])
                  .map(([kind, count]) => (
                    <span
                      key={kind}
                      className={`cursor-pointer rounded-full border px-3 py-1 text-xs transition ${
                        kindFilter === kind ? "border-violet-400 bg-violet-500/20 text-violet-100" : kindBadgeClass(kind as MemoryKind)
                      }`}
                      onClick={() => setKindFilter(kindFilter === kind ? "" : kind as MemoryKind)}
                    >
                      {KIND_LABELS[kind as MemoryKind] ?? kind} <span className="opacity-70">({count})</span>
                    </span>
                  ))}
              </div>
            </article>
          )}
        </>
      )}

      {/* Search + list */}
      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {/* Search bar */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Semantic search across all memories…"
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] py-2.5 pl-9 pr-4 text-sm outline-none placeholder:text-[var(--muted)] focus:border-violet-500/50"
              />
              {searching && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--muted)]">searching…</span>
              )}
            </div>
            <select
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value as MemoryKind | "")}
              className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm outline-none"
            >
              <option value="">All kinds</option>
              {kindOptions.map(([kind, label]) => (
                <option key={kind} value={kind}>{label}</option>
              ))}
            </select>
          </div>

          {/* Results header */}
          {searchResults !== null && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-[var(--muted)]">
                {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} for &ldquo;{query}&rdquo;
              </p>
              <button
                onClick={() => { setQuery(""); setSearchResults(null); }}
                className="text-xs text-[var(--muted)] hover:text-white"
              >
                Clear
              </button>
            </div>
          )}

          {/* Memory list */}
          {loading && !memories.length ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-28 animate-pulse rounded-xl border border-[var(--border)] bg-[var(--surface)]" />
              ))}
            </div>
          ) : displayItems.length === 0 ? (
            <p className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--muted)]">
              {searchResults !== null ? "No memories matched your search." : "No memories stored yet."}
            </p>
          ) : (
            <div className="group space-y-3">
              {displayItems.map((item) => {
                const id = "memory_id" in item ? item.memory_id : item.id;
                const rec = memories.find((m) => m.id === id);
                return (
                  <MemoryCard
                    key={id}
                    memory={item}
                    selected={selected?.id === id}
                    onSelect={() => {
                      if (rec) setSelected(rec === selected ? null : rec);
                    }}
                    onDelete={() => void handleDelete(id)}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selected ? (
          <DetailPanel
            memory={selected}
            onClose={() => setSelected(null)}
            onDelete={() => void handleDelete(selected.id)}
          />
        ) : (
          <aside className="hidden xl:flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--border)] p-8 text-center">
            <ChevronRight size={32} className="text-[var(--muted)] mb-2" />
            <p className="text-sm text-[var(--muted)]">Select a memory to view details</p>
          </aside>
        )}
      </div>
    </div>
  );
}
