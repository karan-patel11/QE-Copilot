import type { Metadata } from "next";

import { AuthGate } from "@/components/AuthGate";
import { AuthProvider } from "@/lib/auth";

import "./globals.css";

export const metadata: Metadata = {
  title: "QE Copilot",
  description: "AI-Powered Test Generation and Defect Triage Platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-gray-900 antialiased">
        {/* Every route renders inside the gate, so no page has to remember to
            check for a session of its own. */}
        <AuthProvider>
          <AuthGate>{children}</AuthGate>
        </AuthProvider>
      </body>
    </html>
  );
}
