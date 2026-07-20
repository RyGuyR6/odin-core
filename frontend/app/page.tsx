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
