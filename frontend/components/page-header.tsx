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
