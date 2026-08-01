import type { Config } from "tailwindcss";

// Semantic tokens only — every colour resolves to a custom property declared in
// app/globals.css (design-tokens.md §8). Components write `text-status-partial-ink`,
// never `text-[#92400E]` and never a stock palette class like `text-amber-700`.
//
// Two consequences, both deliberate: swapping an approximate hex for the real
// extracted value touches one line in globals.css, and a stock Tailwind colour
// appearing in a component becomes a reviewable mistake rather than an invisible
// one.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        status: {
          // T3. `DEFAULT` is the accent (borders, bars, dots — UI components).
          // `ink` is the only value permitted for text.
          success: {
            DEFAULT: "var(--status-success)",
            ink: "var(--status-success-ink)",
            surface: "var(--status-success-surface)",
          },
          failure: {
            DEFAULT: "var(--status-failure)",
            ink: "var(--status-failure-ink)",
            surface: "var(--status-failure-surface)",
          },
          partial: {
            DEFAULT: "var(--status-partial)",
            ink: "var(--status-partial-ink)",
            surface: "var(--status-partial-surface)",
          },
          active: {
            DEFAULT: "var(--status-active)",
            ink: "var(--status-active-ink)",
            surface: "var(--status-active-surface)",
          },
          pending: {
            DEFAULT: "var(--status-pending)",
            ink: "var(--status-pending-ink)",
            surface: "var(--status-pending-surface)",
          },
          muted: {
            DEFAULT: "var(--status-muted)",
            ink: "var(--status-muted-ink)",
            surface: "var(--status-muted-surface)",
          },
        },
        // T7 furniture and the T2 marketing accent.
        rule: "var(--rule)",
        pill: "var(--pill-surface)",
        eyebrow: "var(--eyebrow-ink)",
        highlight: "var(--highlight)",
      },
      fontFamily: {
        // T1: two families, strict role separation. `display` also carries body
        // prose at regular weight — "display" names a role, not a third family.
        display: ["var(--font-display)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        "display-hero": ["48px", { lineHeight: "52px", letterSpacing: "-0.03em" }],
        "display-xl": ["32px", { lineHeight: "36px", letterSpacing: "-0.02em" }],
        "display-lg": ["24px", { lineHeight: "30px", letterSpacing: "-0.015em" }],
        "display-md": ["18px", { lineHeight: "26px", letterSpacing: "-0.01em" }],
        "numeric-xl": ["44px", { lineHeight: "44px", letterSpacing: "-0.02em" }],
        body: ["15px", { lineHeight: "24px" }],
        "body-sm": ["13px", { lineHeight: "20px" }],
        "mono-sm": ["12px", { lineHeight: "18px", letterSpacing: "0.01em" }],
        "mono-xs": ["11px", { lineHeight: "16px", letterSpacing: "0.06em" }],
      },
    },
  },
  plugins: [],
};

export default config;
