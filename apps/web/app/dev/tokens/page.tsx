import { notFound } from "next/navigation";

import { StatusBadge, type BadgeStatus } from "@/components/StatusBadge";

// Development-only. In a production build this route 404s rather than rendering
// the preview, so the page cannot ship even if something links to it. AuthGate
// separately exempts /dev/ only when NODE_ENV !== "production" — two independent
// guards, so neither is load-bearing on its own.
//
// Deliberately NOT `force-dynamic`. With dynamic rendering Next streams the
// response headers before the component body runs, so `notFound()` swaps in the
// 404 *UI* while the status line has already gone out as 200 — a soft 404 that
// looks fine in a browser and wrong to anything checking status codes. Left
// static, `notFound()` is evaluated at build time and the route is emitted as a
// real 404. Verified by building and requesting it, not by reading the docs.

// Contrast figures are transcribed from docs/design/design-tokens.md, where they
// were computed and re-verified against the committed table. They are not
// re-estimated here: a preview that disagrees with the lock would be worse than
// one that omits them.
const SWATCHES = [
  {
    semantic: "success",
    meaning: "COMPLETED · APPROVED · PASSED · confidence ≥ 0.75",
    accent: "#BEF264",
    ink: "#3F6212",
    surface: "#F7FEE7",
    ratio: "7.08:1",
    note: "AAA",
  },
  {
    semantic: "failure",
    meaning: "FAILED · REJECTED · confidence < 0.40",
    accent: "#9B2C1E",
    ink: "#9B2C1E",
    surface: "#FEF2F2",
    ratio: "7.57:1",
    note: "AAA",
  },
  {
    semantic: "partial",
    meaning: "PARTIALLY_COMPLETED · degraded · confidence 0.40–0.74",
    accent: "#D97706",
    ink: "#92400E",
    surface: "#FEF3C7",
    ratio: "7.09:1",
    note: "AAA · accent 3.19:1 = UI only, never text",
  },
  {
    semantic: "active",
    meaning: "RUNNING · WAITING_FOR_PROVIDER · VALIDATING",
    accent: "#1E3A5F",
    ink: "#1E3A5F",
    surface: "#EFF4F9",
    ratio: "11.50:1",
    note: "AAA",
  },
  {
    semantic: "pending",
    meaning: "PENDING · QUEUED · PENDING_REVIEW",
    accent: "#D4D4D8",
    ink: "#52525B",
    surface: "#F4F4F5",
    ratio: "7.73:1",
    note: "AAA",
  },
  {
    semantic: "muted",
    meaning: "CANCELLED · TIMED_OUT",
    accent: "#A1A1AA",
    ink: "#3F3F46",
    surface: "#FAFAFA",
    ratio: "10.44:1",
    note: "AAA",
  },
] as const;

const BADGE_STATES: BadgeStatus[] = [
  "COMPLETED",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "QUEUED",
  "RUNNING",
  "CANCELLED",
];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-mono text-mono-xs uppercase text-eyebrow">{children}</p>
  );
}

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-rule pt-8">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-1 font-display text-display-lg font-semibold">{title}</h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export default function TokenPreviewPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 pb-16">
      <header>
        <Eyebrow>N7-DESIGN v2 · DEV ONLY</Eyebrow>
        <h1 className="mt-1 font-display text-display-xl font-bold">
          Design token preview
        </h1>
        <p className="mt-2 max-w-2xl font-display text-body text-gray-600">
          Every value below resolves through a CSS custom property in{" "}
          <code className="font-mono text-mono-sm">globals.css</code>. Nothing on
          this page uses a stock Tailwind palette class or a raw hex.
        </p>
      </header>

      {/* ---- T3 status palette ---- */}
      <Section eyebrow="T3 · SEMANTIC STATUS PALETTE" title="Six status colours">
        <div className="grid gap-4 sm:grid-cols-2">
          {SWATCHES.map((s) => (
            <div
              key={s.semantic}
              data-testid={`swatch-${s.semantic}`}
              className="overflow-hidden rounded-lg border border-rule"
            >
              {/* Accent bar — the UI-component role, where 3:1 suffices. */}
              <div className="h-2 w-full" style={{ background: s.accent }} />
              <div className="p-4" style={{ background: s.surface }}>
                <div className="flex items-baseline justify-between gap-3">
                  <span
                    className="font-mono text-mono-sm font-medium uppercase"
                    style={{ color: s.ink }}
                  >
                    {s.semantic}
                  </span>
                  <span
                    className="font-mono text-mono-xs tabular"
                    style={{ color: s.ink }}
                  >
                    {s.ratio}
                  </span>
                </div>
                <p
                  className="mt-2 font-mono text-mono-xs"
                  style={{ color: s.ink }}
                >
                  accent {s.accent} · ink {s.ink}
                </p>
                <p className="mt-1 font-mono text-mono-xs text-gray-500">
                  surface {s.surface} · {s.note}
                </p>
                <p className="mt-3 font-display text-body-sm text-gray-600">
                  {s.meaning}
                </p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* ---- StatusBadge ---- */}
      <Section eyebrow="T3 · COMPONENT" title="StatusBadge, every state">
        <div className="flex flex-wrap items-center gap-3">
          {BADGE_STATES.map((state) => (
            <StatusBadge key={state} status={state} />
          ))}
        </div>
        <p className="mt-4 max-w-2xl font-display text-body-sm text-gray-600">
          The status word renders inside every badge, so each reads correctly in
          monochrome — the hard rule that lets <code className="font-mono text-mono-sm">pending</code>{" "}
          and <code className="font-mono text-mono-sm">muted</code> differ only in
          shade, and lets amber sit beside lime.
        </p>
      </Section>

      {/* ---- T1 typography ---- */}
      <Section eyebrow="T1 · TWO-REGISTER TYPOGRAPHY" title="Display and mono">
        <div className="grid gap-8 lg:grid-cols-2">
          <div data-testid="type-display">
            <Eyebrow>DISPLAY · SPACE GROTESK</Eyebrow>
            <p className="mt-3 font-display text-display-xl font-bold">
              Generate tests
            </p>
            <p className="mt-2 font-display text-display-lg font-semibold">
              Requirement decomposition
            </p>
            <p className="mt-2 font-display text-body">
              Body prose sits in the same family at regular weight — “display”
              names a role, not a third family.
            </p>
            <p className="mt-4 font-display text-numeric-xl font-bold tabular">
              277
            </p>
          </div>
          <div data-testid="type-mono">
            <Eyebrow>MONO · JETBRAINS MONO</Eyebrow>
            <p className="mt-3 font-mono text-body">decompose-v1</p>
            <p className="mt-2 font-mono text-mono-sm">
              2026-08-01T00:01:35Z · 84ms
            </p>
            <p className="mt-2 font-mono text-mono-xs uppercase text-eyebrow">
              PROMPT_TEMPLATE_DRIFT
            </p>
            <p className="mt-4 max-w-sm font-display text-body-sm text-gray-600">
              All metadata is mono without exception: timestamps, IDs, status
              labels, error codes, prompt versions — including inside dense
              tables.
            </p>
          </div>
        </div>
      </Section>

      {/* ---- T4 buttons ---- */}
      <Section eyebrow="T4 · BUTTON TIERS" title="Three tiers, one reserved">
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            data-variant="primary"
            className="rounded-full bg-black px-5 py-2 font-display text-body-sm font-medium text-white"
          >
            Approve
          </button>

          <button
            type="button"
            data-variant="secondary"
            className="rounded-full border border-black px-5 py-2 font-display text-body-sm font-medium text-black"
          >
            View detail →
          </button>

          {/* Reserved: the dashed pill marks an action that spends a provider
              call and produces a model_runs row. */}
          <button
            type="button"
            data-variant="ai-action"
            data-ai-action="generate-tests"
            className="inline-flex items-center gap-2 rounded-full border border-dashed border-black px-5 py-2 font-display text-body-sm font-medium text-black"
          >
            <span aria-hidden="true">◈</span> Generate Tests
          </button>

          <button
            type="button"
            data-variant="ai-action"
            data-ai-action="regenerate"
            className="inline-flex items-center gap-2 rounded-full border border-dashed border-black px-5 py-2 font-display text-body-sm font-medium text-black"
          >
            <span aria-hidden="true">◈</span> Regenerate
          </button>
        </div>
        <p className="mt-4 max-w-2xl font-display text-body-sm text-gray-600">
          The dashed variant is the one affordance separating a free action from
          a billed one, so it is restricted to the four allowlisted AI actions.
        </p>
      </Section>

      {/* ---- T7 furniture ---- */}
      <Section eyebrow="T7 · ADOPTED AS-IS" title="Tag pills, dividers, eyebrows">
        <div className="flex flex-wrap items-center gap-2">
          {["entitlement", "playback", "regression", "boundary"].map((tag) => (
            <span
              key={tag}
              data-testid="tag-pill"
              className="inline-flex items-center rounded-full bg-pill px-3 py-1 font-mono text-mono-xs uppercase text-gray-700"
            >
              {tag}
            </span>
          ))}
        </div>
        <p className="mt-4 max-w-2xl font-display text-body-sm text-gray-600">
          The hairline rule above each section header, and the uppercase mono
          eyebrow above each title, are both visible throughout this page.
        </p>
      </Section>
    </div>
  );
}
