// The three T4 button tiers, as components rather than as class strings copied
// between pages — which is the only way the allowlist below can be enforced.

/**
 * The four actions permitted to wear the dashed pill (design-tokens.md T4).
 *
 * Every one of them spends a provider call and produces a `model_runs` row. The
 * dashed border is the single affordance in the product that distinguishes a
 * billed action from a free one, so widening this list is a design decision, not
 * a convenience.
 */
export const AI_ACTIONS = [
  "run-ai-analysis",
  "generate-tests",
  "run-triage",
  "regenerate",
] as const;

export type AiAction = (typeof AI_ACTIONS)[number];

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 py-2 font-display text-body-sm font-medium transition disabled:cursor-not-allowed";

/** Tier 1 — the single main CTA per view. */
export function PrimaryButton({ className = "", ...props }: ButtonProps) {
  return (
    <button
      type="button"
      data-variant="primary"
      className={`${BASE} bg-surface-inverse text-ink-inverse disabled:bg-surface-disabled ${className}`}
      {...props}
    />
  );
}

/** Tier 2 — View, Cancel, Export, Download. */
export function SecondaryButton({ className = "", ...props }: ButtonProps) {
  return (
    <button
      type="button"
      data-variant="secondary"
      className={`${BASE} border border-ink text-ink hover:bg-surface-hover disabled:border-rule-strong disabled:text-ink-subtle ${className}`}
      {...props}
    />
  );
}

/**
 * Tier 3 — reserved. The `action` prop is typed to {@link AiAction}, so a label
 * outside the allowlist is a **compile error**; the Playwright guard in
 * `e2e/design-lock.spec.ts` catches anything that bypasses this component.
 */
export function AiActionButton({
  action,
  className = "",
  children,
  ...props
}: ButtonProps & { action: AiAction }) {
  return (
    <button
      type="button"
      data-variant="ai-action"
      data-ai-action={action}
      className={`${BASE} border border-dashed border-ink text-ink hover:bg-surface-hover disabled:border-rule-strong disabled:text-ink-subtle ${className}`}
      {...props}
    >
      <span aria-hidden="true">◈</span>
      {children}
    </button>
  );
}
