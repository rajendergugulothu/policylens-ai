import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PolicyLens AI",
  description: "Pre-production AI agent policy compliance testing",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f9fafb" }}>
        <header style={{ background: "#1e3a8a", color: "#fff", padding: "12px 24px", display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontWeight: 600, fontSize: 16 }}>PolicyLens AI</span>
          <span style={{ fontSize: 12, opacity: 0.7, background: "#ffffff22", padding: "2px 8px", borderRadius: 4 }}>sandbox</span>
        </header>
        <main style={{ maxWidth: 960, margin: "0 auto", padding: "24px 16px" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
