"use client";
import { useEffect, useState } from "react";

export default function SplashScreen() {
  const [phase, setPhase] = useState<"hidden" | "visible" | "fading" | "gone">("hidden");

  useEffect(() => {
    setPhase("visible");
    const fade = setTimeout(() => setPhase("fading"), 1600);
    const gone = setTimeout(() => setPhase("gone"), 2200);
    return () => { clearTimeout(fade); clearTimeout(gone); };
  }, []);

  if (phase === "hidden" || phase === "gone") return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#0f172a",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        opacity: phase === "fading" ? 0 : 1,
        transition: "opacity 0.6s cubic-bezier(0.4, 0, 0.2, 1)",
        pointerEvents: "none",
      }}
    >
      {/* Shield icon */}
      <div style={{ animation: "splashIcon 0.6s cubic-bezier(0.34,1.56,0.64,1) both" }}>
        <svg
          width="52"
          height="52"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#3b82f6"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ marginBottom: 18, display: "block" }}
        >
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <polyline points="9 12 11 14 15 10" stroke="#60a5fa" strokeWidth="1.5" />
        </svg>
      </div>

      {/* Wordmark */}
      <div
        style={{
          animation: "splashText 0.7s 0.2s cubic-bezier(0.34,1.56,0.64,1) both",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 32,
            fontWeight: 700,
            color: "#f8fafc",
            letterSpacing: "-0.8px",
            fontFamily: "'Inter', system-ui, sans-serif",
            lineHeight: 1,
          }}
        >
          PolicyLens{" "}
          <span style={{ color: "#3b82f6" }}>AI</span>
        </div>
        <div
          style={{
            fontSize: 13,
            color: "#64748b",
            marginTop: 10,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontFamily: "'Inter', system-ui, sans-serif",
            animation: "splashSub 0.5s 0.5s ease both",
          }}
        >
          Pre-production compliance testing
        </div>
      </div>

      {/* Pulse dot */}
      <div
        style={{
          marginTop: 36,
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "#3b82f6",
          animation: "splashPulse 1s 0.8s ease-in-out infinite",
        }}
      />

      <style>{`
        @keyframes splashIcon {
          from { opacity: 0; transform: scale(0.4) translateY(12px); }
          to   { opacity: 1; transform: scale(1) translateY(0); }
        }
        @keyframes splashText {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes splashSub {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes splashPulse {
          0%, 100% { opacity: 0.3; transform: scale(1); }
          50%       { opacity: 1;   transform: scale(1.6); }
        }
      `}</style>
    </div>
  );
}
