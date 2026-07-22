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
  MessageSquare,
  Settings,
  X,
} from "lucide-react";
import { BackendStatus } from "@/components/status/backend-status";

const navigation = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Chat", icon: MessageSquare },
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
          <p className="font-medium text-white">OW-007</p>
          <p className="mt-1">Native AI Chat</p>
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
