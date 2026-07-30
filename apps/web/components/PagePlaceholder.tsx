interface PagePlaceholderProps {
  title: string;
  description: string;
}

// Phase 0 shell: every feature route renders a titled placeholder. Real UI is
// filled in per phase.
export function PagePlaceholder({ title, description }: PagePlaceholderProps) {
  return (
    <section>
      <h1 className="text-2xl font-semibold text-gray-900">{title}</h1>
      <p className="mt-2 max-w-2xl text-gray-600">{description}</p>
      <div className="mt-6 rounded-lg border border-dashed border-gray-300 p-8 text-sm text-gray-500">
        Placeholder — coming in a later phase.
      </div>
    </section>
  );
}
