"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
};

type ConnectedRepository = {
  id: number;
  full_name: string;
  default_branch: string;
};

type WorkspaceProposal = {
  id: string;
  target_path: string;
  operation: string;
  new_path?: string | null;
  approval_status: string;
  approval_note?: string | null;
  reason?: string | null;
  agent?: string | null;
  diff_stats?: {
    added_lines?: number;
    removed_lines?: number;
    language?: string | null;
  };
};

type WorkspaceValidationRun = {
  id: string;
  command_id: string;
  label: string;
  status: string;
  exit_code?: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number;
  timestamp: string;
};

type WorkspaceRecord = {
  id: string;
  task_id?: string | null;
  repository_id: number;
  repository_full_name: string;
  source_branch?: string | null;
  base_commit_sha: string;
  workspace_ref: string;
  status: string;
  created_at: string;
  updated_at: string;
  expires_at?: string | null;
  last_error?: string | null;
  proposals: WorkspaceProposal[];
  approvals: Array<{ id: string; timestamp: string; actor?: string | null; decision: string; note?: string | null }>;
  validation_runs: WorkspaceValidationRun[];
  rollback_history: Array<{ id: string; timestamp: string; actor?: string | null; status: string; reason?: string | null }>;
  audit_history: Array<{ id: string; timestamp: string; action: string; actor?: string | null; note?: string | null }>;
  apply_results: Array<{ id: string; timestamp: string; status: string; message?: string | null }>;
};

type WorkspaceDiff = {
  workspace_id: string;
  full_diff: string;
  truncated: boolean;
  summary: {
    changed_files: number;
    added_lines: number;
    removed_lines: number;
  };
  files: Array<{
    proposal_id: string;
    path: string;
    new_path?: string | null;
    operation: string;
    diff: string;
    added_lines: number;
    removed_lines: number;
    language?: string | null;
  }>;
};

type ValidationCommand = {
  id: string;
  label: string;
  argv: string[];
  cwd: string;
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

async function requestRepositories(): Promise<{ repositories: ConnectedRepository[] }> {
  const response = await fetch("/api/repositories", {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Unable to load repositories (${response.status})`);
  return (await response.json()) as { repositories: ConnectedRepository[] };
}

function badgeClass(status: string): string {
  const value = status.toLowerCase();
  if (value.includes("approved") || value.includes("applied") || value.includes("completed")) {
    return "border-emerald-400/20 bg-emerald-500/10 text-emerald-200";
  }
  if (value.includes("reject") || value.includes("failed") || value.includes("rollback")) {
    return "border-rose-400/20 bg-rose-500/10 text-rose-200";
  }
  if (value.includes("validat") || value.includes("await") || value.includes("pending") || value.includes("proposed")) {
    return "border-amber-400/20 bg-amber-400/10 text-amber-200";
  }
  return "border-violet-400/20 bg-violet-500/10 text-violet-200";
}

export default function Page() {
  const [tasks, setTasks] = useState<ChangeTask[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [repositories, setRepositories] = useState<ConnectedRepository[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [workspaceDiff, setWorkspaceDiff] = useState<WorkspaceDiff | null>(null);
  const [validationCommands, setValidationCommands] = useState<Record<string, ValidationCommand>>({});
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [approvalReasons, setApprovalReasons] = useState<Record<string, string>>({});
  const [description, setDescription] = useState("");
  const [action, setAction] = useState("echo");
  const [message, setMessage] = useState("Planning dry run");
  const [repositoryId, setRepositoryId] = useState<number | null>(null);
  const [workspaceTaskId, setWorkspaceTaskId] = useState("");

  const selectedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ?? null,
    [selectedWorkspaceId, workspaces],
  );

  const loadTasks = useCallback(async () => {
    const data = await request<ChangeTask[]>("/");
    setTasks(data);
  }, []);

  const loadWorkspaces = useCallback(async () => {
    const data = await request<{ workspaces: WorkspaceRecord[] }>("/workspaces");
    setWorkspaces(data.workspaces);
    if (!selectedWorkspaceId && data.workspaces.length > 0) {
      setSelectedWorkspaceId(data.workspaces[0].id);
    }
  }, [selectedWorkspaceId]);

  const loadRepositories = useCallback(async () => {
    const data = await requestRepositories();
    setRepositories(data.repositories);
    if (data.repositories.length > 0 && repositoryId === null) {
      setRepositoryId(data.repositories[0].id);
    }
  }, [repositoryId]);

  const loadWorkspaceDetails = useCallback(async (workspaceId: string) => {
    const [diff, commands] = await Promise.all([
      request<WorkspaceDiff>(`/workspaces/${workspaceId}/diff`),
      request<{ commands: Record<string, ValidationCommand> }>(`/workspaces/${workspaceId}/validation-commands`),
    ]);
    setWorkspaceDiff(diff);
    setValidationCommands(commands.commands);
  }, []);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await Promise.all([loadTasks(), loadWorkspaces(), loadRepositories()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Task Center data");
    } finally {
      setLoading(false);
    }
  }, [loadRepositories, loadTasks, loadWorkspaces]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshAll();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshAll]);

  useEffect(() => {
    if (!selectedWorkspaceId) {
      const timer = window.setTimeout(() => {
        setWorkspaceDiff(null);
        setValidationCommands({});
      }, 0);
      return () => window.clearTimeout(timer);
    }
    const timer = window.setTimeout(() => {
      void loadWorkspaceDetails(selectedWorkspaceId).catch((reason) => {
        setError(reason instanceof Error ? reason.message : "Unable to load workspace details");
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadWorkspaceDetails, selectedWorkspaceId]);

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
          steps: [{ id: "step-1", action, parameters: { message } }],
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

  async function createWorkspace(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!repositoryId) return;
    setBusyKey("workspace-create");
    setError("");
    try {
      const created = await request<WorkspaceRecord>("/workspaces", {
        method: "POST",
        body: JSON.stringify({ repository_id: repositoryId, task_id: workspaceTaskId || undefined }),
      });
      await loadWorkspaces();
      setSelectedWorkspaceId(created.id);
      setWorkspaceTaskId("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create workspace");
    } finally {
      setBusyKey(null);
    }
  }

  async function updateTaskApproval(taskId: string, nextAction: "approve" | "reject") {
    setBusyKey(`task-${taskId}`);
    setError("");
    try {
      await request(`/${taskId}/${nextAction}`, {
        method: "POST",
        body: JSON.stringify({ reason: approvalReasons[taskId] || undefined }),
      });
      await loadTasks();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update task approval");
    } finally {
      setBusyKey(null);
    }
  }

  async function executeTask(taskId: string) {
    setBusyKey(`task-exec-${taskId}`);
    setError("");
    try {
      await request(`/${taskId}/execute`, { method: "POST" });
      await loadTasks();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to execute task");
    } finally {
      setBusyKey(null);
    }
  }

  async function updateWorkspace(workspaceId: string, actionName: "approve" | "reject" | "request-revision", proposalIds?: string[]) {
    setBusyKey(`workspace-${actionName}-${workspaceId}`);
    setError("");
    try {
      await request(`/workspaces/${workspaceId}/${actionName}`, {
        method: "POST",
        body: JSON.stringify({ proposal_ids: proposalIds, note: approvalReasons[workspaceId] || undefined }),
      });
      await loadWorkspaces();
      await loadWorkspaceDetails(workspaceId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update workspace review state");
    } finally {
      setBusyKey(null);
    }
  }

  async function applyWorkspace(workspaceId: string) {
    if (!window.confirm("Apply approved changes to the isolated workspace?")) return;
    setBusyKey(`workspace-apply-${workspaceId}`);
    setError("");
    try {
      await request(`/workspaces/${workspaceId}/apply`, { method: "POST" });
      await loadWorkspaces();
      await loadWorkspaceDetails(workspaceId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to apply workspace changes");
    } finally {
      setBusyKey(null);
    }
  }

  async function validateWorkspace(workspaceId: string, commandIds?: string[]) {
    setBusyKey(`workspace-validate-${workspaceId}`);
    setError("");
    try {
      await request(`/workspaces/${workspaceId}/validate`, {
        method: "POST",
        body: JSON.stringify({ command_ids: commandIds }),
      });
      await loadWorkspaces();
      await loadWorkspaceDetails(workspaceId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to run validation");
    } finally {
      setBusyKey(null);
    }
  }

  async function rollbackWorkspace(workspaceId: string) {
    if (!window.confirm("Roll back the latest applied workspace changes?")) return;
    setBusyKey(`workspace-rollback-${workspaceId}`);
    setError("");
    try {
      await request(`/workspaces/${workspaceId}/rollback`, {
        method: "POST",
        body: JSON.stringify({ reason: "Manual rollback from Task Center" }),
      });
      await loadWorkspaces();
      await loadWorkspaceDetails(workspaceId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to roll back workspace");
    } finally {
      setBusyKey(null);
    }
  }

  const diffByProposalId = useMemo(() => {
    const entries = new Map<string, WorkspaceDiff["files"][number]>();
    for (const diff of workspaceDiff?.files ?? []) entries.set(diff.proposal_id, diff);
    return entries;
  }, [workspaceDiff]);

  return (
    <>
      <PageHeader
        eyebrow="OW-006 · Task Center"
        title="Tasks & Workspaces"
        description="Create dry-run tasks, manage isolated repository workspaces, review diffs, approve files, run validation, and roll back safely."
      />

      {error && (
        <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/10 p-4 text-red-200">
          {error}
        </div>
      )}

      <section className="mb-8 grid gap-6 xl:grid-cols-2">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Create a dry-run planning task</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">Plan safely before any live workspace action.</p>
            </div>
            <button
              type="button"
              onClick={() => void refreshAll()}
              className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:bg-white/5"
            >
              Refresh
            </button>
          </div>
          <form onSubmit={createTask} className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 text-sm">
              <span className="font-medium text-[var(--muted)]">Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2" placeholder="Dry-run planning task" />
            </label>
            <label className="space-y-2 text-sm">
              <span className="font-medium text-[var(--muted)]">Action</span>
              <select value={action} onChange={(event) => setAction(event.target.value)} className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2">
                <option value="echo">echo</option>
                <option value="assert">assert</option>
                <option value="record">record</option>
              </select>
            </label>
            <label className="space-y-2 text-sm md:col-span-2">
              <span className="font-medium text-[var(--muted)]">Description</span>
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} className="min-h-24 w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2" placeholder="Describe the planned task" />
            </label>
            <label className="space-y-2 text-sm md:col-span-2">
              <span className="font-medium text-[var(--muted)]">Message</span>
              <input value={message} onChange={(event) => setMessage(event.target.value)} className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2" placeholder="Message for the action" />
            </label>
            <div className="md:col-span-2">
              <button type="submit" disabled={submitting} className="rounded-lg bg-violet-500 px-4 py-2 font-medium text-white disabled:opacity-60">
                {submitting ? "Creating dry run…" : "Create dry-run task"}
              </button>
            </div>
          </form>
        </article>

        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <div className="mb-4">
            <h2 className="text-xl font-semibold">Create isolated workspace</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">Workspaces are scoped to connected repositories and never edit the source checkout directly.</p>
          </div>
          <form onSubmit={createWorkspace} className="grid gap-4">
            <label className="space-y-2 text-sm">
              <span className="font-medium text-[var(--muted)]">Connected repository</span>
              <select value={repositoryId ?? ""} onChange={(event) => setRepositoryId(Number(event.target.value))} className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2">
                {repositories.map((repository) => (
                  <option key={repository.id} value={repository.id}>
                    {repository.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm">
              <span className="font-medium text-[var(--muted)]">Associated task id</span>
              <input value={workspaceTaskId} onChange={(event) => setWorkspaceTaskId(event.target.value)} className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2" placeholder="Optional task id" />
            </label>
            <div>
              <button type="submit" disabled={!repositoryId || busyKey === "workspace-create"} className="rounded-lg bg-emerald-500 px-4 py-2 font-medium text-white disabled:opacity-60">
                {busyKey === "workspace-create" ? "Creating…" : "Create workspace"}
              </button>
            </div>
          </form>
        </article>
      </section>

      <section className="mb-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-xl font-semibold">Existing tasks</h2>
          <span className="text-sm text-[var(--muted)]">{tasks.length} loaded</span>
        </div>

        {loading ? (
          <p className="text-[var(--muted)]">Loading tasks…</p>
        ) : tasks.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-8 text-center text-[var(--muted)]">No change tasks have been created yet.</div>
        ) : (
          <div className="space-y-4">
            {tasks.map((task) => (
              <article key={task.id} className="rounded-2xl border border-[var(--border)] bg-[rgba(9,10,14,0.65)] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{task.title}</h3>
                      <span className={`rounded-full border px-2.5 py-1 text-xs uppercase tracking-wide ${badgeClass(task.status)}`}>{task.status}</span>
                      <span className={`rounded-full border px-2.5 py-1 text-xs uppercase tracking-wide ${badgeClass(task.approval_status)}`}>approval: {task.approval_status}</span>
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
                      <input value={approvalReasons[task.id] ?? ""} onChange={(event) => setApprovalReasons((current) => ({ ...current, [task.id]: event.target.value }))} className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2" placeholder="Optional reason" />
                    </label>
                    <button type="button" onClick={() => void updateTaskApproval(task.id, "approve")} disabled={busyKey === `task-${task.id}`} className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 disabled:opacity-60">Approve</button>
                    <button type="button" onClick={() => void updateTaskApproval(task.id, "reject")} disabled={busyKey === `task-${task.id}`} className="rounded-lg border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-200 disabled:opacity-60">Reject</button>
                    <button type="button" onClick={() => void executeTask(task.id)} disabled={busyKey === `task-exec-${task.id}` || (!task.dry_run && task.approval_status !== "approved")} className="rounded-lg border border-violet-400/20 bg-violet-500/10 px-3 py-2 text-sm text-violet-200 disabled:opacity-60">Execute</button>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">Repository workspaces</h2>
            <span className="text-sm text-[var(--muted)]">{workspaces.length} loaded</span>
          </div>
          {loading ? (
            <p className="text-[var(--muted)]">Loading workspaces…</p>
          ) : workspaces.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[var(--border)] p-6 text-center text-[var(--muted)]">No repository workspaces exist yet.</div>
          ) : (
            <div className="space-y-3">
              {workspaces.map((workspace) => (
                <button
                  key={workspace.id}
                  type="button"
                  onClick={() => setSelectedWorkspaceId(workspace.id)}
                  className={`w-full rounded-2xl border p-4 text-left transition ${selectedWorkspaceId === workspace.id ? "border-violet-400/40 bg-violet-500/10" : "border-[var(--border)] bg-white/[0.03] hover:bg-white/[0.05]"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{workspace.repository_full_name}</p>
                      <p className="mt-1 text-xs text-[var(--muted)]">{workspace.id}</p>
                    </div>
                    <span className={`rounded-full border px-2 py-1 text-xs uppercase tracking-wide ${badgeClass(workspace.status)}`}>{workspace.status}</span>
                  </div>
                  <p className="mt-2 text-sm text-[var(--muted)]">Base {workspace.base_commit_sha.slice(0, 12)} · {workspace.proposals.length} proposed file actions</p>
                </button>
              ))}
            </div>
          )}
        </article>

        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
          {!selectedWorkspace ? (
            <div className="rounded-2xl border border-dashed border-[var(--border)] p-10 text-center text-[var(--muted)]">Select a workspace to inspect status, diffs, approvals, validation, and rollback history.</div>
          ) : (
            <div className="space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold">{selectedWorkspace.repository_full_name}</h2>
                    <span className={`rounded-full border px-2.5 py-1 text-xs uppercase tracking-wide ${badgeClass(selectedWorkspace.status)}`}>{selectedWorkspace.status}</span>
                  </div>
                  <p className="mt-2 text-sm text-[var(--muted)]">Source branch {selectedWorkspace.source_branch || "unknown"} · base commit {selectedWorkspace.base_commit_sha.slice(0, 12)}</p>
                  {selectedWorkspace.last_error && <p className="mt-2 text-sm text-rose-200">{selectedWorkspace.last_error}</p>}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => void updateWorkspace(selectedWorkspace.id, "approve")} disabled={busyKey === `workspace-approve-${selectedWorkspace.id}`} className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 disabled:opacity-60">Approve all</button>
                  <button type="button" onClick={() => void updateWorkspace(selectedWorkspace.id, "reject")} disabled={busyKey === `workspace-reject-${selectedWorkspace.id}`} className="rounded-lg border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-200 disabled:opacity-60">Reject all</button>
                  <button type="button" onClick={() => void updateWorkspace(selectedWorkspace.id, "request-revision")} disabled={busyKey === `workspace-request-revision-${selectedWorkspace.id}`} className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-sm text-amber-200 disabled:opacity-60">Request revision</button>
                </div>
              </div>

              <label className="block space-y-2 text-sm">
                <span className="font-medium text-[var(--muted)]">Review note</span>
                <input value={approvalReasons[selectedWorkspace.id] ?? ""} onChange={(event) => setApprovalReasons((current) => ({ ...current, [selectedWorkspace.id]: event.target.value }))} className="w-full rounded-lg border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2" placeholder="Optional review or approval note" />
              </label>

              <div className="grid gap-4 lg:grid-cols-3">
                <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Changed files</p>
                  <p className="mt-2 text-2xl font-semibold">{workspaceDiff?.summary.changed_files ?? selectedWorkspace.proposals.length}</p>
                </div>
                <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Added lines</p>
                  <p className="mt-2 text-2xl font-semibold text-emerald-200">+{workspaceDiff?.summary.added_lines ?? 0}</p>
                </div>
                <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Removed lines</p>
                  <p className="mt-2 text-2xl font-semibold text-rose-200">-{workspaceDiff?.summary.removed_lines ?? 0}</p>
                </div>
              </div>

              <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
                <div className="space-y-4">
                  <div className="rounded-2xl border border-[var(--border)] bg-white/[0.03] p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h3 className="font-semibold">Changed-file approvals</h3>
                      <span className="text-sm text-[var(--muted)]">{selectedWorkspace.proposals.length} file actions</span>
                    </div>
                    {selectedWorkspace.proposals.length === 0 ? (
                      <p className="text-sm text-[var(--muted)]">No file actions have been proposed yet.</p>
                    ) : (
                      <div className="space-y-3">
                        {selectedWorkspace.proposals.map((proposal) => {
                          const diff = diffByProposalId.get(proposal.id);
                          return (
                            <div key={proposal.id} className="rounded-xl border border-[var(--border)] bg-[rgba(9,10,14,0.8)] p-4">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <code className="text-sm">{proposal.target_path}</code>
                                    <span className={`rounded-full border px-2 py-1 text-[10px] uppercase tracking-wide ${badgeClass(proposal.approval_status)}`}>{proposal.approval_status}</span>
                                  </div>
                                  <p className="mt-2 text-sm text-[var(--muted)]">{proposal.operation}{proposal.new_path ? ` → ${proposal.new_path}` : ""}{proposal.agent ? ` · ${proposal.agent}` : ""}</p>
                                  {proposal.reason && <p className="mt-1 text-sm text-[var(--muted)]">{proposal.reason}</p>}
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  <button type="button" onClick={() => void updateWorkspace(selectedWorkspace.id, "approve", [proposal.id])} className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">Approve</button>
                                  <button type="button" onClick={() => void updateWorkspace(selectedWorkspace.id, "reject", [proposal.id])} className="rounded-lg border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">Reject</button>
                                  <button type="button" onClick={() => void updateWorkspace(selectedWorkspace.id, "request-revision", [proposal.id])} className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-xs text-amber-200">Revise</button>
                                </div>
                              </div>
                              {diff && (
                                <div className="mt-3 rounded-xl border border-[var(--border)] bg-black/30 p-3">
                                  <div className="mb-2 flex flex-wrap gap-3 text-xs text-[var(--muted)]">
                                    <span>{diff.operation}</span>
                                    <span>+{diff.added_lines}</span>
                                    <span>-{diff.removed_lines}</span>
                                    {diff.language && <span>{diff.language}</span>}
                                  </div>
                                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs text-slate-100">{diff.diff || "No diff preview available."}</pre>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-[var(--border)] bg-white/[0.03] p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h3 className="font-semibold">Full unified diff</h3>
                      {workspaceDiff?.truncated && <span className="text-xs text-[var(--muted)]">Preview truncated</span>}
                    </div>
                    <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl border border-[var(--border)] bg-black/30 p-4 text-xs text-slate-100">{workspaceDiff?.full_diff || "No diff available."}</pre>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="rounded-2xl border border-[var(--border)] bg-white/[0.03] p-4">
                    <h3 className="font-semibold">Apply & validation</h3>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button type="button" onClick={() => void applyWorkspace(selectedWorkspace.id)} disabled={busyKey === `workspace-apply-${selectedWorkspace.id}`} className="rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Apply approved changes</button>
                      <button type="button" onClick={() => void validateWorkspace(selectedWorkspace.id)} disabled={busyKey === `workspace-validate-${selectedWorkspace.id}`} className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-4 py-2 text-sm text-amber-200 disabled:opacity-60">Run default validation</button>
                      <button type="button" onClick={() => void rollbackWorkspace(selectedWorkspace.id)} disabled={busyKey === `workspace-rollback-${selectedWorkspace.id}`} className="rounded-lg border border-rose-400/20 bg-rose-500/10 px-4 py-2 text-sm text-rose-200 disabled:opacity-60">Rollback</button>
                    </div>
                    <div className="mt-4 space-y-2">
                      {Object.values(validationCommands).length === 0 ? (
                        <p className="text-sm text-[var(--muted)]">No allowlisted validation commands were discovered for this workspace.</p>
                      ) : (
                        Object.values(validationCommands).map((command) => (
                          <button key={command.id} type="button" onClick={() => void validateWorkspace(selectedWorkspace.id, [command.id])} className="flex w-full items-center justify-between rounded-xl border border-[var(--border)] bg-[rgba(9,10,14,0.8)] px-3 py-2 text-sm hover:bg-white/5">
                            <span>{command.label}</span>
                            <span className="text-xs text-[var(--muted)]">{command.argv.join(" ")}</span>
                          </button>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-[var(--border)] bg-white/[0.03] p-4">
                    <h3 className="font-semibold">Validation results</h3>
                    {selectedWorkspace.validation_runs.length === 0 ? (
                      <p className="mt-3 text-sm text-[var(--muted)]">No validation runs recorded yet.</p>
                    ) : (
                      <div className="mt-3 space-y-3">
                        {selectedWorkspace.validation_runs.map((run) => (
                          <div key={run.id} className="rounded-xl border border-[var(--border)] bg-[rgba(9,10,14,0.8)] p-3">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <p className="font-medium">{run.label}</p>
                                <p className="text-xs text-[var(--muted)]">{new Date(run.timestamp).toLocaleString()} · {run.duration_ms} ms</p>
                              </div>
                              <span className={`rounded-full border px-2 py-1 text-[10px] uppercase tracking-wide ${badgeClass(run.status)}`}>{run.status}</span>
                            </div>
                            {(run.stdout || run.stderr) && (
                              <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--border)] bg-black/30 p-3 text-xs text-slate-100">{run.stdout || run.stderr}</pre>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-[var(--border)] bg-white/[0.03] p-4">
                    <h3 className="font-semibold">Audit timeline</h3>
                    {selectedWorkspace.audit_history.length === 0 ? (
                      <p className="mt-3 text-sm text-[var(--muted)]">No audit events recorded yet.</p>
                    ) : (
                      <ol className="mt-3 space-y-3">
                        {selectedWorkspace.audit_history.map((event) => (
                          <li key={event.id} className="rounded-xl border border-[var(--border)] bg-[rgba(9,10,14,0.8)] p-3 text-sm">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <span className="font-medium">{event.action}</span>
                              <span className="text-xs text-[var(--muted)]">{new Date(event.timestamp).toLocaleString()}</span>
                            </div>
                            <p className="mt-1 text-[var(--muted)]">{event.actor ? `Actor: ${event.actor}` : "System event"}{event.note ? ` · ${event.note}` : ""}</p>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </article>
      </section>
    </>
  );
}
