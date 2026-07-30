// Left-nav definition — single source of truth for routes and labels.
// Order matches the QE Copilot design's navigation.

export interface NavItem {
  readonly label: string;
  readonly href: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Overview", href: "/" },
  { label: "CI Failures", href: "/ci-failures" },
  { label: "Test Generator", href: "/test-generator" },
  { label: "Defect Triage", href: "/defect-triage" },
  { label: "Knowledge Base", href: "/knowledge-base" },
  { label: "Evaluations", href: "/evaluations" },
  { label: "Analytics", href: "/analytics" },
  { label: "Integrations", href: "/integrations" },
  { label: "System Health", href: "/system-health" },
  { label: "Administration", href: "/administration" },
];
