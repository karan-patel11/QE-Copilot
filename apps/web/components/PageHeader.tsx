// T2's restrained header — the one every functional view uses.
//
// Monospace uppercase eyebrow above a plain bold title. No highlighter mark, no
// hero type, no mixed-weight headline: those belong to the Overview hero and to
// empty states, and `e2e/design-lock.spec.ts` guard (a) fails if one appears
// anywhere else.

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="font-mono text-mono-xs uppercase text-eyebrow">{children}</p>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="flex items-start justify-between gap-6">
      <div>
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="mt-1 font-display text-display-xl font-bold text-ink">{title}</h1>
        {description ? (
          <p className="mt-2 max-w-2xl font-display text-body text-ink-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-3">{actions}</div> : null}
    </header>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  actions,
}: {
  eyebrow: string;
  title: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-4 border-b border-rule pb-3">
      <div>
        <Eyebrow>{eyebrow}</Eyebrow>
        <h2 className="mt-1 font-display text-display-lg font-semibold text-ink">{title}</h2>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function TagPill({ children }: { children: React.ReactNode }) {
  return (
    <span
      data-testid="tag-pill"
      className="inline-flex items-center rounded-full bg-pill px-3 py-1 font-mono text-mono-xs uppercase text-ink-secondary"
    >
      {children}
    </span>
  );
}
