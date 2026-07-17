import type { Metadata } from "next";
import "./globals.css";
import SplashScreen from "./components/SplashScreen";

export const metadata: Metadata = {
  title: "PolicyLens AI",
  description: "Pre-production AI agent policy compliance testing",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SplashScreen />
        <header className="app-header">
          <div className="app-header-logo">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            PolicyLens AI
          </div>
          <div className="app-header-divider" />
          <span style={{ fontSize: 13, color: "rgba(255,255,255,.55)", fontWeight: 400 }}>
            Pre-production compliance testing for AI agents
          </span>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
            <span className="app-header-chip">sandbox</span>
            <span className="app-header-chip" style={{ background: "rgba(34,197,94,.2)", color: "#86efac" }}>
              ● API connected
            </span>
          </div>
        </header>
        <main className="app-main">
          {children}
        </main>
      </body>
    </html>
  );
}
