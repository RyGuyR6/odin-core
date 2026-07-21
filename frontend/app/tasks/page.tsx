"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";

type ChangeStep = {
  id: string;
  action: string;
  parameters: Record<string, unknown>;
  rollback_action?: string | null;
  rollback_parameters?: Record<string, unknown>;
  idempotency_key?: string | null;
};

type ChangeTask = {
  id: string;
  title: string;
  description: string;
  status: string;
  approval_status: string;
  dry_run: boolean;
  confirmed: boolean;
  created_at: string;
  updated_at: string;
  steps: ChangeStep[];
  error?: string | null;
  approval_reason?: string | null;
  approved_by?: string | null;
  rejected_by?: string | null;
  audit_events?: Array<{
    event: string;
    actor?: string | null;
    reason?: string | null;
    timestamp: string;
  }>;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/change-tasks${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: {
      ...(options?.body ? { "content-type": "application/json" } : {}),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {}
    throw new Error(detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export default function Page() {
  const [tasks, setTasks] = useState<ChangeTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [approvalReasons, setApprovalReasons] = useState<Record<string, string>>({});
  const [description, setDescription] = useState("");
  const [action, setAction] = useState("echo");
  const [message, setMessage] = useState("Planning dry run");

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await request<ChangeTask[]>("/");
      setTasks(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load tasks");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadTasks();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadTasks]);

  async function createTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await request("", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim() || "Dry-run planning task",
          description,
          dry_run: true,
          confirmed: false,
          steps: [
            {
              id: "step-1",
              action,
              parameters: { message },
            },
          ],
        }),
      });
      setTitle("");
      setDescription("");
      setAction("echo");
      setMessage("Planning dry run");
      await loadTasks();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create task");
    } finally {
      setSubmitting(false);
    }
  }

  async function updateTaskApproval(taskId: string, action: "approve" | "reject") {
    setBusyTaskId(taskId);
    setError("");
    try {
      await request(`/${taskId}/${action}`, {
        method: "POST",
        body: JSON.stringify({ reason: approvalReasons[taskId] || undefined }),
      });
      await loadTasks();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update approval");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function executeTask(taskId: string) {
    setBusyTaskId(taskId);
    setError("");
    try {
      await request(`/${taskId}/execute`, { method: "POST" });
      await loadTasks();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to execute task");
    } finally {
      setBusyTaskId(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="OW-006 · Task Center"
        title="Tasks"
        description="Review existing change tasks, approve live work, and create planning-only dry runs."
      />

      {error && (
        <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/10 p-4 text-red-200">
          {error}
        </div>
      )}

      <section className="mb-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Create a dry-run planning task</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              This form only plans a task. It does not execute any action.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadTasks()}
            className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:bg-white/5"
          >
            Refresh
          </button>
        </div>

        <form onSubmit={createTask} className="grid gap-4 md:grid-cols-2">
          <label className="space-y-2 text-sm">
            <span className="font-medium text-[var(--muted)]">Title</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2"
              placeholder="Dry-run planning task"
            />
          </label>
          <label className="space-y-2 text-sm">
            <span className="font-medium text-[var(--muted)]">Action</span>
            <select
              value={action}
              onChange={(event) => setAction(event.target.value)}
              className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2"
            >
              <option value="echo">echo</option>
              <option value="assert">assert</option>
              <option value="record">record</option>
            </select>
          </label>
          <label className="space-y-2 text-sm md:col-span-2">
            <span className="font-medium text-[var(--muted)]">Description</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-24 w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2"
              placeholder="Describe the planned task"
            />
          </label>
          <label className="space-y-2 text-sm md:col-span-2">
            <span className="font-medium text-[var(--muted)]">Message</span>
            <input
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2"
              placeholder="Message for the action"
            />
          </label>
          <div className="md:col-span-2">
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-violet-500 px-4 py-2 font-medium text-white disabled:opacity-60"
            >
              {submitting ? "Creating dry run…" : "Create dry-run task"}
            </button>
          </div>
        </form>
      </section>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-xl font-semibold">Existing tasks</h2>
          <span className="text-sm text-[var(--muted)]">{tasks.length} loaded</span>
        </div>

        {loading ? (
          <p className="text-[var(--muted)]">Loading tasks…</p>
        ) : tasks.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-8 text-center text-[var(--muted)]">
            No change tasks have been created yet.
          </div>
        ) : (
          <div className="space-y-4">
            {tasks.map((task) => (
              <article key={task.id} className="rounded-2xl border border-[var(--border)] bg-[rgba(9,10,14,0.65)] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{task.title}</h3>
                      <span className="rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-xs uppercase tracking-wide text-violet-200">
                        {task.status}
                      </span>
                      <span className="rounded-full border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 text-xs uppercase tracking-wide text-amber-200">
                        approval: {task.approval_status}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-[var(--muted)]">{task.description || "No description"}</p>
                  </div>
                  <div className="text-sm text-[var(--muted)]">
                    <p>Dry run: {task.dry_run ? "yes" : "no"}</p>
                    <p>Updated: {new Date(task.updated_at).toLocaleString()}</p>
                  </div>
                </div>
                {!task.dry_run && (
                  <div className="mt-4 grid gap-3 rounded-xl border border-[var(--border)] bg-white/[0.03] p-3 md:grid-cols-[1fr_auto_auto_auto] md:items-end">
                    <label className="space-y-2 text-sm">
                      <span className="font-medium text-[var(--muted)]">Approval note</span>
                      <input
                        value={approvalReasons[task.id] ?? ""}
                        onChange={(event) =>
                          setApprovalReasons((current) => ({ ...current, [task.id]: event.target.value }))
                        }
                        className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2"
                        placeholder="Optional reason"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => void updateTaskApproval(task.id, "approve")}
                      disabled={busyTaskId === task.id}
                      className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 disabled:opacity-60"
                    >
                      {busyTaskId === task.id ? "Working…" : "Approve"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void updateTaskApproval(task.id, "reject")}
                      disabled={busyTaskId === task.id}
                      className="rounded-lg border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-200 disabled:opacity-60"
                    >
                      Reject
                    </button>
                    <button
                      type="button"
                      onClick={() => void executeTask(task.id)}
                      disabled={busyTaskId === task.id || (!task.dry_run && task.approval_status !== "approved")}
                      className="rounded-lg border border-violet-400/20 bg-violet-500/10 px-3 py-2 text-sm text-violet-200 disabled:opacity-60"
                    >
                      Execute
                    </button>
                  </div>
                )}
                <div className="mt-4 space-y-2">
                  {task.steps.map((step) => (
                    <div key={step.id} className="rounded-lg border border-[var(--border)] bg-white/[0.03] p-3 text-sm">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="font-medium">{step.id}</span>
                        <span className="text-violet-200">{step.action}</span>
                      </div>
                      <p className="mt-2 text-[var(--muted)]">
                        {JSON.stringify(step.parameters)}
                      </p>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
