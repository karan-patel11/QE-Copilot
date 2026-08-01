import type { Metadata } from "next";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";

import { AuthGate } from "@/components/AuthGate";
import { AuthProvider } from "@/lib/auth";

import "./globals.css";

// T1 — the two locked registers. `next/font` self-hosts and subsets these at
// build time, so there is no runtime request to Google and no new dependency:
// next/font ships inside Next itself. Each exposes a CSS variable that
// globals.css composes into --font-display / --font-mono.
const display = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
  variable: "--font-space-grotesk",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "700"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "QE Copilot",
  description: "AI-Powered Test Generation and Defect Triage Platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-surface font-display text-ink antialiased">
        {/* Every route renders inside the gate, so no page has to remember to
            check for a session of its own. */}
        <AuthProvider>
          <AuthGate>{children}</AuthGate>
        </AuthProvider>
      </body>
    </html>
  );
}
