// The one stat panel (design-tokens.md T5). Built once, with every section
// optional, because the reference's anatomy is general-purpose enough to serve
// Failure Detail (§11.4), the confidence display (§25), Evaluations (§11.8) and
// the Overview cards from a single implementation.
//
// Anatomy, top to bottom:
//   header row   icon + mono label left, mono metadata right
//   readout      large display numeric
//   bars         label · bar · right-aligned numeric value
//   tiles        stat-tile mini-grid   (this is what StatCard folded into)
//   tags         tag-pill list
//
// The bar rows are the reason this is one component rather than three: §25
// requires a confidence *score*, and the number sits at the right edge of every
// bar by construction here. Three bespoke implementations would be three
// chances to render the bar and drop the number.

export interface StatBar {
  label: string;
  /** 0..1. Rendered as a proportion, and always printed as a number too. */
  value: number;
  /** Overrides the printed value when the raw number is not the useful form. */
  display?: string;
}

export interface StatTile {
  label: string;
  value: string | number;
  hint?: string;
}

export interface StatPanelProps {
  label: string;
  icon?: string;
  meta?: string;
  readout?: { value: string | number; caption?: string };
  bars?: StatBar[];
  tiles?: StatTile[];
  tags?: string[];
  testId?: string;
  children?: React.ReactNode;
}

function Tile({ label, value, hint }: StatTile) {
  return (
    <div data-testid="stat-tile" className="rounded-lg border border-rule p-4">
      <p className="font-mono text-mono-xs uppercase text-ink-subtle">{label}</p>
      <p className="mt-2 font-display text-display-lg font-semibold tabular text-ink">
        {value}
      </p>
      {hint ? (
        <p className="mt-1 font-display text-body-sm text-ink-subtle">{hint}</p>
      ) : null}
    </div>
  );
}

function Bar({ label, value, display }: StatBar) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div data-testid="stat-bar" className="flex items-center gap-3">
      <span className="w-28 shrink-0 font-mono text-mono-xs uppercase text-ink-subtle">
        {label}
      </span>
      <span
        aria-hidden="true"
        className="h-2 flex-1 overflow-hidden rounded-full bg-surface-active"
      >
        <span className="block h-full bg-status-active" style={{ width: `${pct}%` }} />
      </span>
      {/* Never colour or length alone: the number is the signal, the bar is the
          reinforcement (design-tokens.md T3 hard rule, §25). */}
      <span
        data-testid="stat-bar-value"
        className="w-12 shrink-0 text-right font-mono text-mono-sm tabular text-ink"
      >
        {display ?? value.toFixed(2)}
      </span>
    </div>
  );
}

export function StatPanel({
  label,
  icon,
  meta,
  readout,
  bars,
  tiles,
  tags,
  testId,
  children,
}: StatPanelProps) {
  return (
    <section
      data-testid={testId ?? "stat-panel"}
      className="rounded-lg border border-rule"
    >
      <header className="flex items-center justify-between gap-4 border-b border-rule px-4 py-3">
        <span className="flex items-center gap-2 font-mono text-mono-xs uppercase text-ink-secondary">
          {icon ? <span aria-hidden="true">{icon}</span> : null}
          {label}
        </span>
        {meta ? (
          <span className="font-mono text-mono-xs text-ink-subtle">{meta}</span>
        ) : null}
      </header>

      <div className="flex flex-col gap-6 p-4">
        {readout ? (
          <div>
            <p className="font-display text-numeric-xl font-bold tabular text-ink">
              {readout.value}
            </p>
            {readout.caption ? (
              <p className="mt-1 font-mono text-mono-xs uppercase text-ink-subtle">
                {readout.caption}
              </p>
            ) : null}
          </div>
        ) : null}

        {bars?.length ? (
          <div className="flex flex-col gap-2">
            {bars.map((bar) => (
              <Bar key={bar.label} {...bar} />
            ))}
          </div>
        ) : null}

        {tiles?.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {tiles.map((tile) => (
              <Tile key={tile.label} {...tile} />
            ))}
          </div>
        ) : null}

        {tags?.length ? (
          <div className="flex flex-wrap items-center gap-2">
            {tags.map((tag) => (
              <span
                key={tag}
                data-testid="tag-pill"
                className="inline-flex items-center rounded-full bg-pill px-3 py-1 font-mono text-mono-xs uppercase text-ink-secondary"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}

        {children}
      </div>
    </section>
  );
}
