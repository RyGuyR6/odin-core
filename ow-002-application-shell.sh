#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="OW-002"
TITLE="Odin Web Application Shell"
FRONTEND_DIR="frontend"
BACKUP_ROOT=".odin-backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${MILESTONE}-${TIMESTAMP}"
BACKED_UP=0

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$MILESTONE" "$*"; }
ok()   { printf '\033[1;32m[PASS]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; }

find_repo_root() {
  local dir="$PWD"
  while [[ "$dir" != "/" ]]; do
    if [[ -d "$dir/.git" && -d "$dir/backend" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

rollback() {
  local exit_code=$?
  trap - ERR INT TERM
  fail "$TITLE failed (exit $exit_code). Rolling back..."
  if [[ "$BACKED_UP" -eq 1 && -d "$BACKUP_DIR/frontend" ]]; then
    rm -rf "$FRONTEND_DIR"
    cp -a "$BACKUP_DIR/frontend" "$FRONTEND_DIR"
    warn "Restored frontend from $BACKUP_DIR/frontend"
  fi
  exit "$exit_code"
}
trap rollback ERR INT TERM

ROOT="$(find_repo_root || true)"
if [[ -z "$ROOT" ]]; then
  fail "Run this script from inside odin-core (must contain .git/ and backend/)."
  exit 1
fi
cd "$ROOT"

if [[ ! -f "$FRONTEND_DIR/.odin-ow-001" || ! -f "$FRONTEND_DIR/package.json" ]]; then
  fail "OW-001 was not detected. Run OW-001 before OW-002."
  exit 1
fi

command -v node >/dev/null 2>&1 || { fail "Node.js is required."; exit 1; }
command -v npm  >/dev/null 2>&1 || { fail "npm is required."; exit 1; }

log "Starting $TITLE in $ROOT"
mkdir -p "$BACKUP_DIR"
cp -a "$FRONTEND_DIR" "$BACKUP_DIR/frontend"
BACKED_UP=1
ok "Backup created at $BACKUP_DIR/frontend"

mkdir -p \
  "$FRONTEND_DIR/app/api/odin/health" \
  "$FRONTEND_DIR/app/tasks" \
  "$FRONTEND_DIR/app/repositories" \
  "$FRONTEND_DIR/app/activity" \
  "$FRONTEND_DIR/app/settings" \
  "$FRONTEND_DIR/components/navigation" \
  "$FRONTEND_DIR/components/status" \
  "$FRONTEND_DIR/lib" \
  "$FRONTEND_DIR/scripts"

cat > "$FRONTEND_DIR/lib/config.ts" <<'EOF'
const DEFAULT_API_URL = "http://localhost:8000";

function normalizeUrl(value: string): string {
  return value.trim().replace(/\/$/, "");
}

export const odinConfig = {
  appName: process.env.NEXT_PUBLIC_ODIN_APP_NAME?.trim() || "Odin",
  environment:
    process.env.NEXT_PUBLIC_ODIN_ENVIRONMENT?.trim() ||
    process.env.NODE_ENV ||
    "development",
  apiUrl: normalizeUrl(
    process.env.ODIN_API_URL ||
      process.env.NEXT_PUBLIC_ODIN_API_URL ||
      DEFAULT_API_URL,
  ),
  healthPaths: (
    process.env.ODIN_HEALTH_PATHS || "/health,/api/health,/runtime/health"
  )
    .split(",")
    .map((path) => path.trim())
    .filter(Boolean),
  healthTimeoutMs: Number(process.env.ODIN_HEALTH_TIMEOUT_MS || "3500"),
} as const;
EOF

cat > "$FRONTEND_DIR/app/api/odin/health/route.ts" <<'EOF'
import { NextResponse } from "next/server";
import { odinConfig } from "@/lib/config";

type Attempt = {
  path: string;
  status?: number;
  error?: string;
};

export const dynamic = "force-dynamic";

export async function GET() {
  const startedAt = Date.now();
  const attempts: Attempt[] = [];

  for (const path of odinConfig.healthPaths) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const url = `${odinConfig.apiUrl}${normalizedPath}`;
    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(),
      odinConfig.healthTimeoutMs,
    );

    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      });

      attempts.push({ path: normalizedPath, status: response.status });

      if (response.ok) {
        let upstream: unknown = null;
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          upstream = await response.json().catch(() => null);
        }

        return NextResponse.json({
          ok: true,
          state: "connected",
          apiUrl: odinConfig.apiUrl,
          endpoint: normalizedPath,
          latencyMs: Date.now() - startedAt,
          checkedAt: new Date().toISOString(),
          upstream,
        });
      }
    } catch (error) {
      attempts.push({
        path: normalizedPath,
        error: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      clearTimeout(timeout);
    }
  }

  return NextResponse.json(
    {
      ok: false,
      state: "unavailable",
      apiUrl: odinConfig.apiUrl,
      latencyMs: Date.now() - startedAt,
      checkedAt: new Date().toISOString(),
      attempts,
    },
    { status: 503 },
  );
}
EOF

cat > "$FRONTEND_DIR/components/status/backend-status.tsx" <<'EOF'
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
    void check();
    const interval = window.setInterval(() => void check(), 30_000);
    return () => window.clearInterval(interval);
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
EOF

cat > "$FRONTEND_DIR/components/navigation/app-shell.tsx" <<'EOF'
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity,
  Bot,
  FolderGit2,
  LayoutDashboard,
  Menu,
  Settings,
  X,
} from "lucide-react";
import { BackendStatus } from "@/components/status/backend-status";

const navigation = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/tasks", label: "Tasks", icon: Bot },
  { href: "/repositories", label: "Repositories", icon: FolderGit2 },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

function NavLinks({ close }: { close?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="space-y-1" aria-label="Primary navigation">
      {navigation.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={close}
            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
              active
                ? "bg-[var(--accent-soft)] text-violet-100"
                : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-white"
            }`}
          >
            <Icon size={18} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="hidden border-r border-[var(--border)] bg-[rgba(8,11,18,0.82)] p-5 backdrop-blur lg:flex lg:min-h-screen lg:flex-col">
        <Link href="/" className="mb-8 flex items-center gap-3 px-2">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-violet-500 text-white">
            <Bot size={22} />
          </span>
          <span>
            <span className="block font-semibold tracking-wide">ODIN</span>
            <span className="block text-xs text-[var(--muted)]">Control Center</span>
          </span>
        </Link>
        <NavLinks />
        <div className="mt-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 text-xs text-[var(--muted)]">
          <p className="font-medium text-white">OW-002</p>
          <p className="mt-1">Application shell online</p>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/65 lg:hidden" onClick={() => setMobileOpen(false)}>
          <aside
            className="h-full w-[min(82vw,300px)] border-r border-[var(--border)] bg-[var(--background)] p-5"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-8 flex items-center justify-between">
              <span className="flex items-center gap-3 font-semibold">
                <Bot size={22} className="text-violet-300" /> ODIN
              </span>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="rounded-lg border border-[var(--border)] p-2"
                aria-label="Close navigation"
              >
                <X size={18} />
              </button>
            </div>
            <NavLinks close={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[var(--border)] bg-[rgba(8,11,18,0.82)] px-4 backdrop-blur sm:px-6">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="rounded-lg border border-[var(--border)] p-2 lg:hidden"
            aria-label="Open navigation"
          >
            <Menu size={19} />
          </button>
          <div className="hidden lg:block">
            <p className="text-sm text-[var(--muted)]">Remote engineering command center</p>
          </div>
          <BackendStatus compact />
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
EOF

cat > "$FRONTEND_DIR/app/layout.tsx" <<'EOF'
import type { Metadata } from "next";
import { AppShell } from "@/components/navigation/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Odin Control Center",
    template: "%s | Odin",
  },
  description: "Remote command and control for the Odin engineering platform.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
EOF

cat > "$FRONTEND_DIR/components/page-header.tsx" <<'EOF'
export function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow?: string;
  title: string;
  description: string;
}) {
  return (
    <header className="mb-7">
      {eyebrow && <p className="mb-2 text-sm font-medium text-violet-300">{eyebrow}</p>}
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted)] sm:text-base">
        {description}
      </p>
    </header>
  );
}
EOF

cat > "$FRONTEND_DIR/app/page.tsx" <<'EOF'
import { Activity, Bot, FolderGit2, ShieldCheck } from "lucide-react";
import { BackendStatus } from "@/components/status/backend-status";
import { PageHeader } from "@/components/page-header";

const metrics = [
  { label: "Active tasks", value: "0", detail: "Task queue arrives in OW-004", icon: Bot },
  { label: "Repositories", value: "1", detail: "odin-core configured", icon: FolderGit2 },
  { label: "Approvals", value: "0", detail: "No work waiting", icon: ShieldCheck },
  { label: "Recent events", value: "—", detail: "Activity feed arrives next", icon: Activity },
];

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        eyebrow="OW-002 · Application shell"
        title="Odin Control Center"
        description="Monitor connectivity and navigate the capabilities that will turn Odin into your remote autonomous engineering platform."
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(({ label, value, detail, icon: Icon }) => (
          <article key={label} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[var(--muted)]">{label}</p>
              <Icon size={18} className="text-violet-300" />
            </div>
            <p className="mt-4 text-3xl font-semibold">{value}</p>
            <p className="mt-2 text-sm text-[var(--muted)]">{detail}</p>
          </article>
        ))}
      </section>

      <section className="mt-5 grid gap-5 lg:grid-cols-[1fr_1.3fr]">
        <BackendStatus />
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <h2 className="font-medium">Foundation progress</h2>
          <div className="mt-5 space-y-4">
            {[
              ["Web foundation", "Complete"],
              ["Responsive shell", "Complete"],
              ["Backend status proxy", "Complete"],
              ["Authentication", "Next"],
            ].map(([label, state]) => (
              <div key={label} className="flex items-center justify-between border-b border-[var(--border)] pb-3 last:border-0 last:pb-0">
                <span className="text-sm">{label}</span>
                <span className="rounded-full bg-[var(--accent-soft)] px-2.5 py-1 text-xs text-violet-200">{state}</span>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}
EOF

make_placeholder() {
  local dir="$1" title="$2" description="$3" milestone="$4"
  cat > "$FRONTEND_DIR/app/$dir/page.tsx" <<EOF
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="$milestone"
        title="$title"
        description="$description"
      />
      <section className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface)] p-8 text-center">
        <p className="font-medium">Capability scaffolded</p>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">
          This route is ready for its dedicated milestone. Navigation and mobile behavior are active now.
        </p>
      </section>
    </>
  );
}
EOF
}

make_placeholder "tasks" "Tasks" "Create, approve, monitor, cancel, and review Odin's engineering work." "Task Center · OW-004"
make_placeholder "repositories" "Repositories" "Browse the repositories, branches, files, and pull requests managed by Odin." "Repository Explorer · OW-008"
make_placeholder "activity" "Activity" "Follow task execution, GitHub actions, system events, and audit history." "Activity Feed · OW-003"
make_placeholder "settings" "Settings" "Configure providers, safety policies, deployments, integrations, and environments." "Configuration"

cat > "$FRONTEND_DIR/.env.example" <<'EOF'
# Browser-visible API URL. For local development, FastAPI normally runs here.
NEXT_PUBLIC_ODIN_API_URL=http://localhost:8000

# Server-side override used by the Next.js health proxy.
# On Render this should be your deployed FastAPI URL, later api.odincore.net.
ODIN_API_URL=http://localhost:8000

# Comma-separated FastAPI health endpoints. Odin Web tries each in order.
ODIN_HEALTH_PATHS=/health,/api/health,/runtime/health
ODIN_HEALTH_TIMEOUT_MS=3500

NEXT_PUBLIC_ODIN_APP_NAME=Odin
NEXT_PUBLIC_ODIN_ENVIRONMENT=development
ODIN_WEB_ORIGIN=http://localhost:3000
EOF

cat > "$FRONTEND_DIR/scripts/verify-ow-002.mjs" <<'EOF'
import { access, readFile } from "node:fs/promises";

const required = [
  "app/api/odin/health/route.ts",
  "components/navigation/app-shell.tsx",
  "components/status/backend-status.tsx",
  "app/tasks/page.tsx",
  "app/repositories/page.tsx",
  "app/activity/page.tsx",
  "app/settings/page.tsx",
  "lib/config.ts",
];

for (const path of required) {
  await access(path);
}

const shell = await readFile("components/navigation/app-shell.tsx", "utf8");
for (const route of ["/tasks", "/repositories", "/activity", "/settings"]) {
  if (!shell.includes(route)) throw new Error(`Navigation is missing ${route}`);
}

const health = await readFile("app/api/odin/health/route.ts", "utf8");
if (!health.includes("odinConfig.healthPaths")) {
  throw new Error("Health route is not using configured health paths");
}

console.log("OW-002 structural verification passed");
EOF

node - <<'NODE'
const fs = require('fs');
const path = 'frontend/package.json';
const pkg = JSON.parse(fs.readFileSync(path, 'utf8'));
pkg.scripts = pkg.scripts || {};
pkg.scripts['verify:ow-002'] = 'node scripts/verify-ow-002.mjs';
pkg.scripts.verify = 'npm run lint && npm run typecheck && npm run verify:ow-002 && npm run build';
fs.writeFileSync(path, JSON.stringify(pkg, null, 2) + '\n');
NODE

cat >> "$FRONTEND_DIR/README.md" <<'EOF'

## OW-002 application shell

OW-002 adds responsive desktop/mobile navigation and a same-origin health proxy at `/api/odin/health`.

Configure the backend in `.env.local`:

```bash
ODIN_API_URL=http://localhost:8000
NEXT_PUBLIC_ODIN_API_URL=http://localhost:8000
```

The proxy tries `/health`, `/api/health`, and `/runtime/health` by default. Override these with `ODIN_HEALTH_PATHS` when necessary.
EOF

printf '%s\n' "$MILESTONE" > "$FRONTEND_DIR/.odin-ow-002"

log "Ensuring dependencies are installed..."
(
  cd "$FRONTEND_DIR"
  npm install --no-audit --no-fund
)

log "Running OW-002 structural checks, lint, typecheck, and production build..."
(
  cd "$FRONTEND_DIR"
  npm run verify
)

trap - ERR INT TERM
ok "$TITLE installed successfully"
printf '\n'
printf 'Location:       %s/%s\n' "$ROOT" "$FRONTEND_DIR"
printf 'Backup:         %s/%s\n' "$ROOT" "$BACKUP_DIR"
printf 'Development:    cd frontend && npm run dev\n'
printf 'Open locally:   http://localhost:3000\n'
printf 'Health proxy:   http://localhost:3000/api/odin/health\n'
printf 'API setting:    frontend/.env.local -> ODIN_API_URL\n'
printf '\nNext milestone: OW-003 authentication and protected remote access.\n'
