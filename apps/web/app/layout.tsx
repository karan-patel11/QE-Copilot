import type { Metadata } from "next";

import { Sidebar } from "@/components/Sidebar";

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
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex-1 overflow-auto p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
