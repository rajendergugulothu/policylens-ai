"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Workspace, type Policy } from "@/lib/api";

export default function WorkspacePage({ params }: { params: { id: string } }) {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [policyText, setPolicyText] = useState("");
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.workspaces.get(params.id).then(setWs);
    api.policies.list(params.id).then(setPolicies);
  }, [params.id]);

  async function handleUpload() {
    if (!policyText.trim()) return;
    setUploading(true);
    setMsg("");
    try {
      const result = await api.policies.uploadText(params.id, policyText, title || undefined);
      setPolicies((prev) => [result.policy, ...prev]);
      setPolicyText("");
      setTitle("");
      setMsg(`Uploaded: ${result.message}`);
    } catch (e: unknown) {
      setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Link href="/" style={{ color: "#1e3a8a", fontSize: 13 }}>← Workspaces</Link>
      </div>
      <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 4 }}>{ws?.name ?? "Loading…"}</h1>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 28 }}>
        {ws?.workflow_type} · {ws?.is_sandbox ? "Sandbox mode" : "Production mode"}
      </p>

      {/* Upload policy */}
      <div style={{ background: "#fff", border: "0.5px solid #e5e7eb", borderRadius: 10, padding: "18px 20px", marginBottom: 28 }}>
        <h2 style={{ fontSize: 15, fontWeight: 500, marginBottom: 12, marginTop: 0 }}>Upload policy</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Policy title (optional)"
          style={{ width: "100%", padding: "8px 12px", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 13, marginBottom: 8, boxSizing: "border-box" }}
        />
        <textarea
          value={policyText}
          onChange={(e) => setPolicyText(e.target.value)}
          placeholder="Paste your policy text here…"
          rows={8}
          style={{ width: "100%", padding: "8px 12px", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 13, fontFamily: "monospace", resize: "vertical", boxSizing: "border-box" }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
          <button
            onClick={handleUpload}
            disabled={uploading || !policyText.trim()}
            style={{ padding: "8px 18px", background: "#1e3a8a", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, cursor: "pointer", opacity: uploading ? 0.6 : 1 }}
          >
            {uploading ? "Uploading…" : "Upload policy"}
          </button>
          {msg && <span style={{ fontSize: 12, color: msg.startsWith("Error") ? "#991b1b" : "#166534" }}>{msg}</span>}
        </div>
      </div>

      {/* Policy list */}
      <h2 style={{ fontSize: 15, fontWeight: 500, marginBottom: 12 }}>Policies ({policies.length})</h2>
      {policies.length === 0 ? (
        <p style={{ color: "#9ca3af", fontSize: 13 }}>No policies yet. Upload one above.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {policies.map((p) => (
            <Link key={p.id} href={`/policy/${p.id}/rules`} style={{ textDecoration: "none", color: "inherit" }}>
              <div style={{ background: "#fff", border: "0.5px solid #e5e7eb", borderRadius: 10, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}>
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>
                    {p.title ?? "Untitled policy"} <span style={{ fontSize: 11, color: "#9ca3af" }}>v{p.version}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>
                    {p.source_format} · {p.rule_count} rule{p.rule_count !== 1 ? "s" : ""} ({p.approved_rule_count} approved)
                    {p.open_ambiguity_count > 0 && (
                      <span style={{ marginLeft: 8, color: "#92400e", background: "#fef3c7", padding: "1px 6px", borderRadius: 4 }}>
                        {p.open_ambiguity_count} ambiguity flag{p.open_ambiguity_count > 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                </div>
                <span style={{ fontSize: 12, color: "#1e3a8a" }}>Review rules →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
