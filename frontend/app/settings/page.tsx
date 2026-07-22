import Link from "next/link";
import { Bot, ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/page-header";

const sections = [
  {
    href: "/settings/ai",
    icon: Bot,
    title: "AI Platform",
    description:
      "OpenAI provider status, model routing, execution profiles, and diagnostics.",
  },
];

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Configure providers, safety policies, deployments, integrations, and environments."
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sections.map(({ href, icon: Icon, title, description }) => (
          <Link
            key={href}
            href={href}
            className="group flex items-start gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 transition hover:border-violet-400/30 hover:bg-violet-400/5"
          >
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
              <Icon size={18} className="text-violet-200" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium">{title}</p>
              <p className="mt-0.5 text-sm text-[var(--muted)]">{description}</p>
            </div>
            <ChevronRight
              size={16}
              className="mt-1 shrink-0 text-[var(--muted)] transition group-hover:translate-x-0.5 group-hover:text-violet-200"
            />
          </Link>
        ))}
      </div>
    </>
  );
}
