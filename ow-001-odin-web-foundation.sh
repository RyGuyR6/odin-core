#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="OW-001"
TITLE="Odin Web Foundation"
FRONTEND_DIR="frontend"
BACKUP_ROOT=".odin-backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${MILESTONE}-${TIMESTAMP}"
CREATED_FRONTEND=0
BACKED_UP_FRONTEND=0

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

  if [[ "$BACKED_UP_FRONTEND" -eq 1 && -d "$BACKUP_DIR/frontend" ]]; then
    rm -rf "$FRONTEND_DIR"
    cp -a "$BACKUP_DIR/frontend" "$FRONTEND_DIR"
    warn "Restored frontend from $BACKUP_DIR/frontend"
  elif [[ "$CREATED_FRONTEND" -eq 1 ]]; then
    rm -rf "$FRONTEND_DIR"
    warn "Removed newly-created frontend directory"
  fi

  exit "$exit_code"
}
trap rollback ERR INT TERM

ROOT="$(find_repo_root || true)"
if [[ -z "$ROOT" ]]; then
  fail "Run this script from inside the odin-core repository (the repo must contain .git/ and backend/)."
  exit 1
fi
cd "$ROOT"

log "Starting $TITLE in $ROOT"

command -v node >/dev/null 2>&1 || { fail "Node.js is required. Install Node.js 20.9 or newer."; exit 1; }
command -v npm  >/dev/null 2>&1 || { fail "npm is required."; exit 1; }

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
NODE_MINOR="$(node -p 'process.versions.node.split(".")[1]')"
if (( NODE_MAJOR < 20 || (NODE_MAJOR == 20 && NODE_MINOR < 9) )); then
  fail "Node.js 20.9+ is required. Found $(node --version)."
  exit 1
fi
ok "Node $(node --version)"

mkdir -p "$BACKUP_DIR"
if [[ -d "$FRONTEND_DIR" ]]; then
  if [[ -f "$FRONTEND_DIR/.odin-ow-001" ]]; then
    log "Existing OW-001 installation detected; refreshing managed files safely."
  else
    log "Backing up existing frontend directory."
  fi
  cp -a "$FRONTEND_DIR" "$BACKUP_DIR/frontend"
  BACKED_UP_FRONTEND=1
else
  mkdir -p "$FRONTEND_DIR"
  CREATED_FRONTEND=1
fi

mkdir -p \
  "$FRONTEND_DIR/app" \
  "$FRONTEND_DIR/components" \
  "$FRONTEND_DIR/lib" \
  "$FRONTEND_DIR/public"

cat > "$FRONTEND_DIR/package.json" <<'EOF'
{
  "name": "odin-web",
  "version": "0.1.0",
  "private": true,
  "engines": {
    "node": ">=20.9.0"
  },
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "verify": "npm run lint && npm run typecheck && npm run build"
  },
  "dependencies": {
    "next": "16.2.10",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.1.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "eslint": "^9.0.0",
    "eslint-config-next": "16.2.10",
    "postcss": "^8.0.0",
    "tailwindcss": "^4.1.0",
    "typescript": "^5.7.0"
  }
}
EOF

cat > "$FRONTEND_DIR/tsconfig.json" <<'EOF'
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", ".next/types/**/*.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
EOF

cat > "$FRONTEND_DIR/next-env.d.ts" <<'EOF'
/// <reference types="next" />
/// <reference types="next/image-types/global" />

// This file is generated for Next.js TypeScript support.
EOF

cat > "$FRONTEND_DIR/next.config.ts" <<'EOF'
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
EOF

cat > "$FRONTEND_DIR/postcss.config.mjs" <<'EOF'
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
EOF

cat > "$FRONTEND_DIR/eslint.config.mjs" <<'EOF'
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
EOF

cat > "$FRONTEND_DIR/.gitignore" <<'EOF'
node_modules/
.next/
out/
.env
.env.local
.env.*.local
npm-debug.log*
.DS_Store
EOF

cat > "$FRONTEND_DIR/.env.example" <<'EOF'
# Local FastAPI backend
NEXT_PUBLIC_ODIN_API_URL=http://localhost:8000

# Used later when OW authentication is added
ODIN_WEB_ORIGIN=http://localhost:3000
EOF

cat > "$FRONTEND_DIR/lib/api.ts" <<'EOF'
const DEFAULT_API_URL = "http://localhost:8000";

export const ODIN_API_URL = (
  process.env.NEXT_PUBLIC_ODIN_API_URL ?? DEFAULT_API_URL
).replace(/\/$/, "");

export class OdinApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "OdinApiError";
  }
}

export async function odinFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const response = await fetch(`${ODIN_API_URL}${normalizedPath}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init.headers,
    },
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new OdinApiError(
      `Odin API request failed with status ${response.status}`,
      response.status,
      payload,
    );
  }

  return payload as T;
}
EOF

cat > "$FRONTEND_DIR/app/layout.tsx" <<'EOF'
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Odin Control Center",
  description: "Remote command and control for the Odin engineering platform.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
EOF

cat > "$FRONTEND_DIR/app/globals.css" <<'EOF'
@import "tailwindcss";

:root {
  color-scheme: dark;
  --background: #080b12;
  --surface: #111722;
  --surface-2: #171f2d;
  --border: #263247;
  --foreground: #f4f7fb;
  --muted: #91a0b8;
  --accent: #8b5cf6;
  --accent-soft: rgba(139, 92, 246, 0.16);
  --success: #34d399;
}

* {
  box-sizing: border-box;
}

html,
body {
  min-height: 100%;
}

body {
  margin: 0;
  background:
    radial-gradient(circle at top right, rgba(139, 92, 246, 0.13), transparent 32rem),
    var(--background);
  color: var(--foreground);
  font-family: Arial, Helvetica, sans-serif;
}

button,
a,
input,
textarea,
select {
  font: inherit;
}
EOF

cat > "$FRONTEND_DIR/app/page.tsx" <<'EOF'
import { Activity, Bot, Github, Server, TerminalSquare } from "lucide-react";

const cards = [
  { label: "Runtime", value: "Foundation ready", icon: Server },
  { label: "GitHub", value: "Backend integration next", icon: Github },
  { label: "Task Engine", value: "API wiring next", icon: Activity },
  { label: "AI Planner", value: "Provider layer planned", icon: Bot },
];

export default function Home() {
  return (
    <main className="mx-auto min-h-screen max-w-7xl px-5 py-8 sm:px-8">
      <header className="flex flex-col gap-5 border-b border-[var(--border)] pb-7 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--accent-soft)] px-3 py-1 text-sm text-violet-200">
            <TerminalSquare size={15} /> OW-001 installed
          </div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Odin Control Center</h1>
          <p className="mt-2 max-w-2xl text-[var(--muted)]">
            The remote interface for planning, approving, and monitoring Odin&apos;s engineering work.
          </p>
        </div>
        <div className="inline-flex w-fit items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
          Web foundation healthy
        </div>
      </header>

      <section className="grid gap-4 py-7 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(({ label, value, icon: Icon }) => (
          <article key={label} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <Icon className="mb-5 text-violet-300" size={21} />
            <p className="text-sm text-[var(--muted)]">{label}</p>
            <p className="mt-1 font-medium">{value}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="text-lg font-medium">What this milestone established</h2>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {[
              "Next.js App Router",
              "Strict TypeScript",
              "Tailwind CSS",
              "Typed Odin API client",
              "Production standalone build",
              "Docker-ready structure",
            ].map((item) => (
              <div key={item} className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 text-sm">
                {item}
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="text-lg font-medium">Next capability</h2>
          <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
            OW-002 will add the responsive application shell, navigation, configuration handling, and a live backend connection indicator.
          </p>
          <div className="mt-5 rounded-xl border border-violet-400/30 bg-[var(--accent-soft)] p-4 text-sm text-violet-100">
            Target domain: odincore.net
          </div>
        </article>
      </section>
    </main>
  );
}
EOF

cat > "$FRONTEND_DIR/Dockerfile" <<'EOF'
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
EOF

cat > "$FRONTEND_DIR/.dockerignore" <<'EOF'
node_modules
.next
.git
.env*
npm-debug.log*
EOF

cat > "$FRONTEND_DIR/README.md" <<'EOF'
# Odin Web

Odin's remote control center.

## Local development

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000.

## Validation

```bash
npm run verify
```

## Production

The application is configured for a standalone Next.js build and includes a multi-stage Dockerfile.
EOF

printf '%s\n' "$MILESTONE" > "$FRONTEND_DIR/.odin-ow-001"

# Keep root Git tracking clean and make the installer itself easy to commit.
touch .gitignore
for entry in "frontend/node_modules/" "frontend/.next/" "frontend/.env" "frontend/.env.local"; do
  grep -qxF "$entry" .gitignore || printf '%s\n' "$entry" >> .gitignore
done

log "Installing frontend dependencies..."
(
  cd "$FRONTEND_DIR"
  npm install --no-audit --no-fund
)

log "Running lint, typecheck, and production build..."
(
  cd "$FRONTEND_DIR"
  npm run verify
)

trap - ERR INT TERM

ok "$TITLE installed successfully"
printf '\n'
printf 'Location:        %s/%s\n' "$ROOT" "$FRONTEND_DIR"
printf 'Backup:          %s/%s\n' "$ROOT" "$BACKUP_DIR"
printf 'Development:     cd frontend && npm run dev\n'
printf 'Open locally:    http://localhost:3000\n'
printf 'Backend target:  http://localhost:8000 (edit frontend/.env.local later)\n'
printf 'Domain target:   https://odincore.net\n'
printf '\nNext: commit the generated frontend, then proceed to OW-002.\n'
