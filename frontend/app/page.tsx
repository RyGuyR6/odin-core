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
