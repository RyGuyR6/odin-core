"use client";

import { Activity, CheckCircle2, Clock3, Shield, TriangleAlert, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import {
  getToolManagerData,
  type ToolApproval,
  type ToolExecution,
  type ToolHealth,
  type ToolManagerData,
} from "@/lib/api/tools";

function badgeClass(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("success") || normalized.includes("healthy") || normalized.includes("approved") || normalized.includes("safe")) {
    return "border-emerald-400/20 bg-emerald-500/10 text-emerald-200";
  }
  if (normalized.includes("fail") || normalized.includes("denied") || normalized.includes("restricted") || normalized.includes("timed")) {
    return "border-rose-400/20 bg-rose-500/10 text-rose-200";
  }
  if (normalized.includes("approval") || normalized.includes("pending") || normalized.includes("await")) {
    return "border-amber-400/20 bg-amber-400/10 text-amber-200";
  }
  return "border-violet-400/20 bg-violet-500/10 text-violet-200";
}

function StatCard({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Wrench }) {
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

function EmptyState({ message }: { message: string }) {
  return <p className="rounded-xl border border-dashed border-[var(--border)] p-6 text-sm text-[var(--muted)]">{message}</p>;
}

function HealthPanel({ items }: { items: ToolHealth[] }) {
  if (!items.length) return <EmptyState message="No tool health records available." />;
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <article key={item.tool_name} className="rounded-xl border border-[var(--border)] bg-black/10 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-medium">{item.tool_name}</p>
              <p className="text-xs text-[var(--muted)]">{item.category} · v{item.version}</p>
            </div>
            <span className={`rounded-full border px-2.5 py-1 text-xs capitalize ${badgeClass(item.status)}`}>{item.status}</span>
          </div>
          {item.detail && <p className="mt-3 text-sm text-[var(--muted)]">{item.detail}</p>}
        </article>
      ))}
    </div>
  );
}

function ExecutionTable({ executions }: { executions: ToolExecution[] }) {
  if (!executions.length) return <EmptyState message="No recent executions recorded." />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
          <tr>
            <th className="pb-3 pr-4">Tool</th>
            <th className="pb-3 pr-4">Status</th>
            <th className="pb-3 pr-4">Actor</th>
            <th className="pb-3 pr-4">Duration</th>
            <th className="pb-3">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {executions.map((execution) => (
            <tr key={execution.id}>
              <td className="py-3 pr-4 align-top">
                <p className="font-medium">{execution.tool_name}</p>
                <p className="text-xs text-[var(--muted)]">{execution.workspace_id}</p>
              </td>
              <td className="py-3 pr-4 align-top">
                <span className={`rounded-full border px-2.5 py-1 text-xs capitalize ${badgeClass(execution.approval_status ?? execution.status)}`}>
                  {execution.approval_status ?? execution.status}
                </span>
              </td>
              <td className="py-3 pr-4 align-top text-[var(--muted)]">{execution.actor_id}</td>
              <td className="py-3 pr-4 align-top text-[var(--muted)]">{execution.elapsed_ms ? `${Math.round(execution.elapsed_ms)} ms` : "—"}</td>
              <td className="py-3 align-top text-[var(--muted)]">{new Date(execution.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ApprovalList({ approvals }: { approvals: ToolApproval[] }) {
  if (!approvals.length) return <EmptyState message="No approval requests are waiting." />;
  return (
    <div className="space-y-3">
      {approvals.map((approval) => (
        <article key={approval.id} className="rounded-xl border border-[var(--border)] bg-black/10 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-medium">{approval.tool_name}</p>
              <p className="text-xs text-[var(--muted)]">{approval.reason}</p>
            </div>
            <span className={`rounded-full border px-2.5 py-1 text-xs capitalize ${badgeClass(approval.status)}`}>{approval.status}</span>
          </div>
          <div className="mt-3 text-xs text-[var(--muted)]">
            Requested by {approval.actor_id} · expires {new Date(approval.expires_at).toLocaleString()}
          </div>
        </article>
      ))}
    </div>
  );
}

export default function ToolsPage() {
  const [data, setData] = useState<ToolManagerData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestIdRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestIdRef.current += 1;
    const requestId = requestIdRef.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const next = await getToolManagerData(controller.signal);
      if (requestId !== requestIdRef.current) return;
      setData(next);
      setError("");
    } catch (nextError) {
      if (controller.signal.aborted || requestId !== requestIdRef.current) return;
      setError(nextError instanceof Error ? nextError.message : "Tool Manager unavailable");
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void load();
    }, 0);
    const id = window.setInterval(() => {
      void load();
    }, 15000);
    return () => {
      controllerRef.current?.abort();
      window.clearTimeout(initialLoad);
      window.clearInterval(id);
    };
  }, [load]);

  const permissionCounts = useMemo(() => {
    const counts = { safe: 0, approval: 0, restricted: 0 };
    for (const item of data?.permissions.permissions ?? []) {
      if (item.permission_level === "safe") counts.safe += 1;
      else if (item.permission_level === "approval_required") counts.approval += 1;
      else counts.restricted += 1;
    }
    return counts;
  }, [data]);

  return (
    <div className="space-y-7">
      <PageHeader
        eyebrow="OIC-009"
        title="Tool Manager"
        description="The Agent Tool Platform is Odin’s single execution layer for filesystem, terminal, git, GitHub, repository, and web capabilities."
      />

      {loading && !data ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((item) => <div key={item} className="h-32 animate-pulse rounded-2xl border border-[var(--border)] bg-[var(--surface)]" />)}</div> : null}

      {!loading && !data ? (
        <div className="rounded-2xl border border-rose-400/20 bg-rose-400/5 p-6">
          <TriangleAlert className="text-rose-300" />
          <p className="mt-3">{error}</p>
          <button onClick={() => void load()} className="mt-4 rounded-lg border border-[var(--border)] px-3 py-2">Retry</button>
        </div>
      ) : null}

      {data ? (
        <>
          {error ? <p className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-3 text-sm text-amber-100">Refresh failed: {error}</p> : null}

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Installed tools" value={String(data.telemetry.tools_registered)} icon={Wrench} />
            <StatCard label="Total executions" value={String(data.telemetry.total_executions)} icon={Activity} />
            <StatCard label="Awaiting approval" value={String(data.telemetry.awaiting_approval)} icon={Shield} />
            <StatCard label="Average runtime" value={`${Math.round(data.telemetry.average_elapsed_ms)} ms`} icon={Clock3} />
          </section>

          <section className="grid gap-5 xl:grid-cols-[1.35fr_.65fr]">
            <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
              <div className="flex items-center justify-between">
                <h2 className="font-medium">Installed tools</h2>
                <CheckCircle2 size={18} />
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
                    <tr>
                      <th className="pb-3 pr-4">Tool</th>
                      <th className="pb-3 pr-4">Category</th>
                      <th className="pb-3 pr-4">Permissions</th>
                      <th className="pb-3">Risk</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {data.tools.map((tool) => (
                      <tr key={tool.name}>
                        <td className="py-3 pr-4 align-top">
                          <p className="font-medium">{tool.name}</p>
                          <p className="text-xs text-[var(--muted)]">{tool.description}</p>
                        </td>
                        <td className="py-3 pr-4 align-top text-[var(--muted)]">{tool.category}</td>
                        <td className="py-3 pr-4 align-top">
                          <span className={`rounded-full border px-2.5 py-1 text-xs capitalize ${badgeClass(tool.permission_level)}`}>{tool.permission_level.replaceAll("_", " ")}</span>
                        </td>
                        <td className="py-3 align-top">
                          <span className={`rounded-full border px-2.5 py-1 text-xs capitalize ${badgeClass(tool.risk)}`}>{tool.risk}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>

            <div className="space-y-5">
              <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
                <h2 className="font-medium">Permission model</h2>
                <div className="mt-4 grid grid-cols-3 gap-3">
                  <div className="rounded-xl border border-[var(--border)] p-3"><p className="text-xs text-[var(--muted)]">Safe</p><p className="mt-1 text-xl font-semibold">{permissionCounts.safe}</p></div>
                  <div className="rounded-xl border border-[var(--border)] p-3"><p className="text-xs text-[var(--muted)]">Approval</p><p className="mt-1 text-xl font-semibold">{permissionCounts.approval}</p></div>
                  <div className="rounded-xl border border-[var(--border)] p-3"><p className="text-xs text-[var(--muted)]">Restricted</p><p className="mt-1 text-xl font-semibold">{permissionCounts.restricted}</p></div>
                </div>
                <ul className="mt-4 space-y-2 text-sm text-[var(--muted)]">
                  <li>Shell enabled: {data.permissions.shell_enabled ? "yes" : "no"}</li>
                  <li>Python enabled: {data.permissions.python_enabled ? "yes" : "no"}</li>
                  <li>Approval on writes: {data.permissions.require_approval_for_writes ? "yes" : "no"}</li>
                  <li>Approval on shell: {data.permissions.require_approval_for_shell ? "yes" : "no"}</li>
                </ul>
              </article>

              <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
                <h2 className="font-medium">Approval requests</h2>
                <div className="mt-4">
                  <ApprovalList approvals={data.approvals} />
                </div>
              </article>
            </div>
          </section>

          <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <h2 className="font-medium">Recent executions</h2>
            <div className="mt-4">
              <ExecutionTable executions={data.executions} />
            </div>
          </article>

          <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <h2 className="font-medium">Tool health</h2>
            <div className="mt-4">
              <HealthPanel items={data.health} />
            </div>
          </article>
        </>
      ) : null}
    </div>
  );
}
