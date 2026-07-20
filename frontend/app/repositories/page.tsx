import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <>
      <PageHeader
        eyebrow="Repository Explorer · OW-008"
        title="Repositories"
        description="Browse the repositories, branches, files, and pull requests managed by Odin."
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
