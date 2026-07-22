"use client";

import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Cpu,
  FlaskConical,
  Loader2,
  RefreshCw,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  fetchLlmConfig,
  fetchLlmDiagnostics,
  fetchLlmHealth,
  testLlmConnection,
  type LlmConfig,
  type LlmDiagnostics,
  type LlmHealth,
  type LlmTestConnectionResult,
  type ProviderHealth,
} from "@/lib/api/llm";
import {
  fetchOperationsHistory,
  fetchOperationsOverview,
  fetchOperationsProviders,
  type OperationEvent,
  type OperationsOverview,
  type ProviderOperationsHealth,
} from "@/lib/api/aiOperations";

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

const authBadge: Record<string, string> = {
  ok: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
  missing_key: "border-rose-400/25 bg-rose-400/10 text-rose-200",
  invalid_key: "border-rose-400/25 bg-rose-400/10 text-rose-200",
  unknown: "border-amber-400/25 bg-amber-400/10 text-amber-200",
};

function StatusBadge({
  ok,
  label,
}: {
  ok: boolean;
  label?: string;
}) {
  const cls = ok
    ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
    : "border-rose-400/25 bg-rose-400/10 text-rose-200";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {ok ? (
        <CheckCircle2 size={11} />
      ) : (
        <AlertCircle size={11} />
      )}
      {label ?? (ok ? "OK" : "Error")}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Connection Status card
// ---------------------------------------------------------------------------

function ConnectionStatus({ health }: { health: LlmHealth }) {
  const provider = health.providers[0] as ProviderHealth | undefined;
  const isUp = provider?.available ?? false;
  const authStatus = provider?.auth_status ?? "unknown";

  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted)]">Connection</p>
        {isUp ? (
          <Wifi size={18} className="text-emerald-300" />
        ) : (
          <WifiOff size={18} className="text-rose-300" />
        )}
      </div>
      <p className="mt-4 text-2xl font-semibold">
        {isUp ? "Connected" : "Disconnected"}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${authBadge[authStatus] ?? authBadge["unknown"]}`}
        >
          {authStatus === "ok"
            ? "Auth OK"
            : authStatus === "missing_key"
              ? "No API key"
              : authStatus === "invalid_key"
                ? "Invalid key"
                : "Auth unknown"}
        </span>
        {provider?.latency_ms != null && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-0.5 text-xs text-[var(--muted)]">
            {Math.round(provider.latency_ms)} ms
          </span>
        )}
      </div>
      {provider?.consecutive_failures ? (
        <p className="mt-3 text-xs text-rose-300">
          {provider.consecutive_failures} consecutive failure
          {provider.consecutive_failures !== 1 ? "s" : ""}
        </p>
      ) : null}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Active Profile card
// ---------------------------------------------------------------------------

const profileIcon: Record<string, typeof Zap> = {
  economy: Zap,
  balanced: Cpu,
  maximum: FlaskConical,
};

function ActiveProfile({ config }: { config: LlmConfig }) {
  const profile = config.default_execution_profile;
  const Icon = profileIcon[profile] ?? Cpu;
  const modelMap: Record<string, string> = {
    economy: config.economy_model,
    balanced: config.balanced_model,
    maximum: config.primary_model,
  };
  const activeModel = modelMap[profile] ?? config.primary_model;

  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted)]">Execution Profile</p>
        <Icon size={18} className="text-violet-200" />
      </div>
      <p className="mt-4 text-2xl font-semibold capitalize">{profile}</p>
      <p className="mt-1 font-mono text-sm text-[var(--muted)]">
        {activeModel}
      </p>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Models overview card
// ---------------------------------------------------------------------------

function ModelsCard({ config }: { config: LlmConfig }) {
  const rows = [
    { role: "Primary", model: config.primary_model },
    { role: "Balanced", model: config.balanced_model },
    { role: "Economy", model: config.economy_model },
    { role: "Embedding", model: config.embedding_model },
  ];

  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted)]">Configured Models</p>
        <Bot size={18} className="text-violet-200" />
      </div>
      <ul className="mt-4 space-y-2.5">
        {rows.map(({ role, model }) => (
          <li
            key={role}
            className="flex items-center justify-between text-sm"
          >
            <span className="text-[var(--muted)]">{role}</span>
            <span className="font-mono text-xs">{model}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Diagnostics panel
// ---------------------------------------------------------------------------

function DiagnosticsPanel({
  diagnostics,
}: {
  diagnostics: LlmDiagnostics;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-sm font-medium text-[var(--muted)]">Diagnostics</h2>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-[var(--muted)]">Capability entries</dt>
          <dd className="mt-0.5 font-mono text-sm">
            {diagnostics.capabilities_registered}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--muted)]">OIC-009 tools</dt>
          <dd className="mt-0.5 font-mono text-sm">
            {diagnostics.oic009_tools_registered}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--muted)]">Task types</dt>
          <dd className="mt-0.5 font-mono text-sm">
            {diagnostics.available_task_types.length}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--muted)]">Routing profiles</dt>
          <dd className="mt-0.5 font-mono text-sm">
            {diagnostics.routing_profiles.join(", ")}
          </dd>
        </div>
      </dl>

      {diagnostics.configured_model_warnings.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-400/25 bg-amber-400/5 p-3">
          <p className="text-xs font-medium text-amber-200">
            Model warnings
          </p>
          <ul className="mt-1 space-y-1">
            {diagnostics.configured_model_warnings.map((w, i) => (
              <li key={i} className="text-xs text-[var(--muted)]">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function OperationsOverviewCard({ overview }: { overview: OperationsOverview }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-sm font-medium text-[var(--muted)]">Usage & Cost</h2>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-[var(--muted)]">Total requests</dt>
          <dd className="mt-0.5 font-mono text-sm">{overview.total_requests}</dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--muted)]">Total tokens</dt>
          <dd className="mt-0.5 font-mono text-sm">{overview.total_tokens}</dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--muted)]">Avg latency</dt>
          <dd className="mt-0.5 font-mono text-sm">
            {Math.round(overview.average_latency_ms)} ms
          </dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--muted)]">Estimated cost</dt>
          <dd className="mt-0.5 font-mono text-sm">
            ${overview.total_estimated_cost_usd.toFixed(4)}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function ProviderCards({ items }: { items: ProviderOperationsHealth[] }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-sm font-medium text-[var(--muted)]">Provider Health</h2>
      <ul className="mt-4 space-y-3">
        {items.map((item) => (
          <li key={item.provider} className="rounded-xl border border-[var(--border)] p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">{item.provider}</p>
              <StatusBadge ok={item.available} />
            </div>
            <p className="mt-1 text-xs text-[var(--muted)]">
              avg {Math.round(item.average_latency_ms)} ms • failure{" "}
              {(item.failure_rate * 100).toFixed(1)}%
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RecentActivity({ items }: { items: OperationEvent[] }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-sm font-medium text-[var(--muted)]">Recent AI Activity</h2>
      <ul className="mt-4 space-y-2">
        {items.map((item) => (
          <li
            key={item.request_id}
            className="flex items-center justify-between rounded-lg border border-[var(--border)] px-3 py-2 text-xs"
          >
            <div>
              <p className="font-mono">{item.model}</p>
              <p className="text-[var(--muted)]">
                {item.task_type ?? "chat"} • {Math.round(item.latency_ms)} ms
              </p>
            </div>
            <StatusBadge ok={item.status === "success"} />
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Test Connection panel
// ---------------------------------------------------------------------------

function TestConnectionPanel() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LlmTestConnectionResult | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setResult(null);
    try {
      const r = await testLlmConnection();
      setResult(r);
    } catch (e) {
      setResult({
        success: false,
        message: e instanceof Error ? e.message : "Request failed",
        auth_status: "unknown",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-[var(--muted)]">
          Test Connection
        </h2>
        <button
          onClick={() => void run()}
          disabled={loading}
          className="flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium transition hover:border-violet-400/30 hover:bg-violet-400/10 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <ChevronRight size={13} />
          )}
          Run test
        </button>
      </div>

      {result && (
        <div className="mt-4">
          <div className="flex items-center gap-2">
            <StatusBadge ok={result.success} label={result.success ? "Pass" : "Fail"} />
            {result.latency_ms != null && (
              <span className="text-xs text-[var(--muted)]">
                {Math.round(result.latency_ms)} ms
              </span>
            )}
          </div>
          <p className="mt-2 text-sm text-[var(--muted)]">{result.message}</p>
          {result.configured_model_status && (
            <ul className="mt-3 space-y-1">
              {Object.entries(result.configured_model_status)
                .filter(([k]) => k !== "note")
                .map(([role, available]) => (
                  <li
                    key={role}
                    className="flex items-center justify-between text-xs"
                  >
                    <span className="capitalize text-[var(--muted)]">
                      {role.replace(/_/g, " ")}
                    </span>
                    <StatusBadge
                      ok={available === true}
                      label={available === true ? "Available" : "Unavailable"}
                    />
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AiSettingsPage() {
  const [health, setHealth] = useState<LlmHealth | null>(null);
  const [config, setConfig] = useState<LlmConfig | null>(null);
  const [diagnostics, setDiagnostics] = useState<LlmDiagnostics | null>(null);
  const [operationsOverview, setOperationsOverview] =
    useState<OperationsOverview | null>(null);
  const [operationsProviders, setOperationsProviders] = useState<
    ProviderOperationsHealth[]
  >([]);
  const [recentOperations, setRecentOperations] = useState<OperationEvent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [h, c, d] = await Promise.all([
        fetchLlmHealth(),
        fetchLlmConfig(),
        fetchLlmDiagnostics(),
      ]);
      const [overview, providers, history] = await Promise.all([
        fetchOperationsOverview(),
        fetchOperationsProviders(),
        fetchOperationsHistory(8),
      ]);
      setHealth(h);
      setConfig(c);
      setDiagnostics(d);
      setOperationsOverview(overview);
      setOperationsProviders(providers);
      setRecentOperations(history);
      setError("");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to load AI platform data",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(id);
  }, [load]);

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-[var(--muted)]">
            AI Platform
          </p>
          <h1 className="mt-1 text-2xl font-semibold">AI Settings</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            OpenAI provider status, model routing, and diagnostics.
          </p>
        </div>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium transition hover:border-violet-400/30 hover:bg-violet-400/10 disabled:opacity-50"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-400/25 bg-rose-400/5 p-4 text-sm text-rose-200">
          {error}
        </div>
      )}

      {loading && !health ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-40 animate-pulse rounded-2xl border border-[var(--border)] bg-[var(--surface)]"
            />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {health && <ConnectionStatus health={health} />}
            {config && <ActiveProfile config={config} />}
            {config && <ModelsCard config={config} />}
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {diagnostics && (
              <DiagnosticsPanel diagnostics={diagnostics} />
            )}
            <TestConnectionPanel />
            {operationsOverview && (
              <OperationsOverviewCard overview={operationsOverview} />
            )}
            <ProviderCards items={operationsProviders} />
            <RecentActivity items={recentOperations} />
          </div>
        </>
      )}
    </>
  );
}
