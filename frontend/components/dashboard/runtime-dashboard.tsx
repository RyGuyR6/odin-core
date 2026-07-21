"use client";

import { Activity, Bot, Cpu, FolderGit2, HardDrive, ListChecks, MemoryStick, RefreshCw, Server, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { getRuntime, type RuntimeData } from "@/lib/api/runtime";

const badge = {
  healthy: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
  degraded: "border-amber-400/25 bg-amber-400/10 text-amber-200",
  offline: "border-rose-400/25 bg-rose-400/10 text-rose-200",
};

const agentStatusLabel: Record<RuntimeData["agents"][number]["status"], string> = {
  offline: "Offline",
  starting: "Starting",
  idle: "Idle",
  running: "Running",
  waiting_approval: "Waiting for approval",
  succeeded: "Succeeded",
  failed: "Failed",
};

function sanitizeErrorMessage(value: string) {
  return value.replace(/<[^>]*>/g, "").replace(/[\u0000-\u001f\u007f]/g, " ").trim();
}

function Metric({ label, value, progress, icon: Icon }: { label: string; value: string; progress?: number; icon: typeof Cpu }) {
  return <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
    <div className="flex items-center justify-between"><p className="text-sm text-[var(--muted)]">{label}</p><Icon size={18} className="text-violet-200" /></div>
    <p className="mt-4 text-3xl font-semibold">{value}</p>
    {progress !== undefined && <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/5"><div className="h-full rounded-full bg-cyan-300" style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} /></div>}
  </article>;
}

export function RuntimeDashboard() {
  const [data, setData] = useState<RuntimeData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestIdRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const unmountedRef = useRef(false);
  const load = useCallback(async () => {
    requestIdRef.current += 1;
    const requestId = requestIdRef.current;
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      const runtime = await getRuntime(controller.signal);
      if (unmountedRef.current || requestId !== requestIdRef.current) return;
      setData(runtime);
      setError("");
    }
    catch (e) {
      if (controller.signal.aborted || unmountedRef.current || requestId !== requestIdRef.current) return;
      setError(e instanceof Error ? e.message : "Runtime unavailable");
    }
    finally {
      if (!unmountedRef.current && requestId === requestIdRef.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    unmountedRef.current = false;
    const initialLoad = window.setTimeout(() => {
      void load();
    }, 0);

    const id = window.setInterval(() => {
      void load();
    }, 10000);

    return () => {
      unmountedRef.current = true;
      abortControllerRef.current?.abort();
      window.clearTimeout(initialLoad);
      window.clearInterval(id);
    };
  }, [load]);

  if (loading && !data) return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0,1,2,3].map(i => <div key={i} className="h-40 animate-pulse rounded-2xl border border-[var(--border)] bg-[var(--surface)]" />)}</div>;
  if (!data) return <div className="rounded-2xl border border-rose-400/20 bg-rose-400/5 p-6"><TriangleAlert className="text-rose-300" /><p className="mt-3">{sanitizeErrorMessage(error)}</p><button onClick={() => void load()} className="mt-4 rounded-lg border border-[var(--border)] px-3 py-2">Retry</button></div>;

  const m = data.runtime.metrics;
  const tasks = Object.entries(data.tasks);
  const currentTask = data.recent_activity[0]?.message ?? "No active task";
  const lastHeartbeat = data.proxy?.checkedAt ? new Date(data.proxy.checkedAt).toLocaleString() : "Unavailable";
  return <div className="space-y-5">
    <section className="flex flex-col gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:flex-row sm:items-center sm:justify-between">
      <div><div className="flex items-center gap-3"><h2 className="text-lg font-semibold">Odin runtime</h2><span className={`rounded-full border px-3 py-1 text-xs capitalize ${badge[data.runtime.status]}`}>{data.runtime.status}</span></div><p className="mt-2 text-sm text-[var(--muted)]">{data.runtime.environment} · v{data.runtime.version} · 10-second polling</p><p className="mt-1 text-xs text-[var(--muted)]">Current task: {currentTask}</p><p className="mt-1 text-xs text-[var(--muted)]">Last heartbeat: {lastHeartbeat}</p></div>
      <button onClick={() => void load()} className="rounded-lg border border-[var(--border)] p-2"><RefreshCw size={16} /></button>
    </section>
    {error && <p className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-3 text-sm text-amber-100">Refresh failed: {sanitizeErrorMessage(error)}. Showing cached data.</p>}
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="CPU" value={`${m.cpu_percent.toFixed(1)}%`} progress={m.cpu_percent} icon={Cpu} />
      <Metric label="Memory" value={`${m.memory_percent.toFixed(1)}%`} progress={m.memory_percent} icon={MemoryStick} />
      <Metric label="Disk" value={`${m.disk_percent.toFixed(1)}%`} progress={m.disk_percent} icon={HardDrive} />
      <Metric label="API latency" value={`${data.proxy?.latencyMs ?? 0} ms`} icon={Server} />
    </section>
    <section className="grid gap-5 xl:grid-cols-[1.35fr_.65fr]">
      <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5"><h2 className="font-medium">Agent registry</h2><div className="mt-4 grid gap-3 md:grid-cols-2">{data.agents.map(a => <div key={a.id} className="rounded-xl border border-[var(--border)] bg-black/10 p-4"><div className="flex gap-3"><Bot size={18} className="text-violet-200" /><div><p className="font-medium">{a.name} <span className="ml-2 text-xs text-[var(--muted)]">{agentStatusLabel[a.status]}</span></p><p className="mt-1 text-xs text-[var(--muted)]">{a.description}</p></div></div></div>)}</div></article>
      <div className="space-y-5"><article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5"><div className="flex justify-between"><h2>Tasks</h2><ListChecks size={18} /></div><div className="mt-4 grid grid-cols-2 gap-3">{tasks.map(([k,v]) => <div key={k} className="rounded-xl border border-[var(--border)] p-3"><p className="text-xs capitalize text-[var(--muted)]">{k}</p><p className="mt-1 text-xl font-semibold">{v}</p></div>)}</div></article><article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5"><div className="flex justify-between"><h2>Repositories</h2><FolderGit2 size={18} /></div><p className="mt-4 text-3xl font-semibold">{data.repositories.connected}</p><p className="text-sm text-[var(--muted)]">Connected</p></article></div>
    </section>
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5"><div className="flex justify-between"><h2>Recent activity</h2><Activity size={18} /></div>{data.recent_activity.length ? <div className="mt-4 divide-y divide-[var(--border)]">{data.recent_activity.map(x => <div key={x.id} className="flex justify-between py-3 text-sm"><span>{x.message}</span><span className="text-xs text-[var(--muted)]">{new Date(x.timestamp).toLocaleString()}</span></div>)}</div> : <p className="mt-5 rounded-xl border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted)]">No recent activity.</p>}</article>
  </div>;
}
