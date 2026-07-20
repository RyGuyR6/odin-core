"use client";

import { useCallback, useEffect, useState } from "react";
import { CircleAlert, LoaderCircle, RefreshCw, Wifi } from "lucide-react";

type HealthPayload = {
  ok: boolean;
  state: "connected" | "unavailable";
  apiUrl: string;
  endpoint?: string;
  latencyMs: number;
  checkedAt: string;
};

type ConnectionState = "checking" | "connected" | "unavailable";

export function BackendStatus({ compact = false }: { compact?: boolean }) {
  const [state, setState] = useState<ConnectionState>("checking");
  const [health, setHealth] = useState<HealthPayload | null>(null);

  const check = useCallback(async () => {
    setState((current) => (current === "connected" ? current : "checking"));
    try {
      const response = await fetch("/api/odin/health", { cache: "no-store" });
      const payload = (await response.json()) as HealthPayload;
      setHealth(payload);
      setState(response.ok && payload.ok ? "connected" : "unavailable");
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    const initialCheck = window.setTimeout(() => {
      void check();
    }, 0);

    const interval = window.setInterval(() => {
      void check();
    }, 30_000);

    return () => {
      window.clearTimeout(initialCheck);
      window.clearInterval(interval);
    };
  }, [check]);

  const status = {
    checking: {
      label: "Checking API",
      className: "text-amber-200 bg-amber-400/10 border-amber-400/25",
      icon: LoaderCircle,
    },
    connected: {
      label: "API connected",
      className: "text-emerald-200 bg-emerald-400/10 border-emerald-400/25",
      icon: Wifi,
    },
    unavailable: {
      label: "API unavailable",
      className: "text-rose-200 bg-rose-400/10 border-rose-400/25",
      icon: CircleAlert,
    },
  }[state];

  const Icon = status.icon;

  if (compact) {
    return (
      <button
        type="button"
        onClick={() => void check()}
        className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${status.className}`}
        title={health ? `${health.apiUrl} · ${health.latencyMs} ms` : status.label}
      >
        <Icon className={state === "checking" ? "animate-spin" : ""} size={16} />
        <span className="hidden sm:inline">{status.label}</span>
      </button>
    );
  }

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-[var(--muted)]">Odin API</p>
          <div className="mt-2 flex items-center gap-2">
            <Icon
              className={state === "checking" ? "animate-spin text-amber-300" : "text-violet-300"}
              size={20}
            />
            <p className="font-medium">{status.label}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void check()}
          className="rounded-lg border border-[var(--border)] p-2 text-[var(--muted)] hover:text-white"
          aria-label="Refresh API status"
        >
          <RefreshCw size={16} />
        </button>
      </div>
      <p className="mt-4 break-all text-sm text-[var(--muted)]">
        {health?.apiUrl ?? "Waiting for connection check..."}
      </p>
      {health && (
        <p className="mt-2 text-xs text-[var(--muted)]">
          {health.endpoint ? `${health.endpoint} · ` : ""}
          {health.latencyMs} ms · {new Date(health.checkedAt).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
