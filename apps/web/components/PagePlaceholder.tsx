interface PagePlaceholderProps {
  title: string;
  description: string;
}

// Phase 0 shell: every feature route renders a titled placeholder. Real UI is
// filled in per phase.
export function PagePlaceholder({ title, description }: PagePlaceholderProps) {
  return (
    <section>
      <h1 className="text-2xl font-semibold text-ink">{title}</h1>
      <p className="mt-2 max-w-2xl text-ink-muted">{description}</p>
      <div className="mt-6 rounded-lg border border-dashed border-rule-strong p-8 text-sm text-ink-subtle">
        Placeholder — coming in a later phase.
      </div>
    </section>
  );
}
