"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Workspace, type Policy, type EvaluationRun } from "@/lib/api";

export default function WorkspacePage({ params }: { params: { id: string } }) {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [policyText, setPolicyText] = useState("");
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);

  useEffect(() => {
    api.workspaces.get(params.id).then(setWs);
    api.policies.list(params.id).then((p) => {
      setPolicies(p);
      if (p.length === 0) setShowUpload(true);
    });
    api.evaluations.list(params.id).then(setRuns).catch(() => {});
  }, [params.id]);

  async function handleUpload() {
    if (!policyText.trim()) return;
    setUploading(true);
    setMsg(null);
    try {
      const result = await api.policies.uploadText(params.id, policyText, title || undefined);
      setPolicies((prev) => [result.policy, ...prev]);
      setPolicyText("");
      setTitle("");
      setMsg({ text: "Policy uploaded successfully.", ok: true });
      setShowUpload(false);
    } catch (e: unknown) {
      setMsg({ text: `Error: ${e instanceof Error ? e.message : String(e)}`, ok: false });
    } finally {
      setUploading(false);
    }
  }

  const totalRules = policies.reduce((s, p) => s + (p.rule_count ?? 0), 0);
  const approvedRules = policies.reduce((s, p) => s + (p.approved_rule_count ?? 0), 0);
  const openFlags = policies.reduce((s, p) => s + (p.open_ambiguity_count ?? 0), 0);

  return (
    <div>
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <Link href="/">Workspaces</Link>
        <span>›</span>
        <span>{ws?.name ?? "…"}</span>
      </div>

      {/* Page header */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1>{ws?.name ?? "Loading…"}</h1>
          <p style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className={`badge badge-${ws?.workflow_type === "refund" ? "approved" : "pending"}`}>{ws?.workflow_type}</span>
            <span style={{ color: "var(--text-3)" }}>·</span>
            <span>{ws?.is_sandbox ? "Sandbox mode" : "Production mode"}</span>
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowUpload((v) => !v)}>
          {showUpload ? "Cancel" : "+ Upload policy"}
        </button>
      </div>

      {/* Stats */}
      {policies.length > 0 && (
        <div className="stat-strip">
          {[
            { label: "Policies", val: policies.length, color: "var(--brand)" },
            { label: "Total rules", val: totalRules, color: "var(--text)" },
            { label: "Approved rules", val: approvedRules, color: "#15803d" },
            { label: "Ambiguity flags", val: openFlags, color: openFlags > 0 ? "#b45309" : "#94a3b8" },
          ].map(({ label, val, color }) => (
            <div key={label} className="stat-card">
              <div className="stat-label">{label}</div>
              <div className="stat-value" style={{ color }}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Flash message */}
      {msg && (
        <div className={`alert ${msg.ok ? "alert-success" : "alert-error"}`}>
          {msg.ok ? "✓" : "✗"} {msg.text}
        </div>
      )}

      {/* Upload panel */}
      {showUpload && (
        <div className="card upload-card" style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16, marginTop: 0 }}>Upload policy document</h2>
          <div style={{ marginBottom: 10 }}>
            <label className="field-label">Policy title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. ShopFast Return & Refund Policy v4.2"
              className="input"
            />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label className="field-label">Policy text</label>
            <textarea
              value={policyText}
              onChange={(e) => setPolicyText(e.target.value)}
              placeholder="Paste your full policy document here…"
              rows={9}
              className="textarea"
              style={{ fontFamily: "ui-monospace, monospace", fontSize: 13 }}
            />
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={handleUpload} disabled={uploading || !policyText.trim()} className="btn btn-primary">
              {uploading ? "Uploading…" : "Upload policy"}
            </button>
            <button onClick={() => setShowUpload(false)} className="btn btn-ghost">Cancel</button>
          </div>
        </div>
      )}

      {/* Evaluation runs */}
      {runs.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          <div className="section-header">Evaluation Runs ({runs.length})</div>
          <div className="ws-list">
            {runs.map((run) => (
              <Link key={run.id} href={`/evaluation/${run.id}`} className="card-link">
                <div className="card ws-card">
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, flexShrink: 0 }}>🧪</div>
                    <div>
                      <div className="ws-card-title">{run.version_label ?? "Evaluation run"}</div>
                      <div className="ws-card-meta">
                        <span className={`badge ${run.status === "completed" ? "badge-approved" : run.status === "failed" ? "badge-rejected" : "badge-pending"}`}>{run.status}</span>
                        {run.status === "completed" && <>
                          <span>·</span>
                          <span style={{ color: (run.decision_accuracy_pct ?? 0) >= 90 ? "#15803d" : "#be123c" }}>
                            {run.decision_accuracy_pct?.toFixed(1)}% accuracy
                          </span>
                          <span>·</span>
                          <span style={{ color: run.critical_violations > 0 ? "#be123c" : "#15803d" }}>
                            {run.critical_violations} critical violation{run.critical_violations !== 1 ? "s" : ""}
                          </span>
                        </>}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 13, color: "var(--brand)", fontWeight: 500 }}>View report</span>
                    <span style={{ color: "var(--text-3)", fontSize: 18 }}>›</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Policy list */}
      <div className="section-header">Policies ({policies.length})</div>
      {policies.length === 0 ? (
        <div className="empty-state card" style={{ padding: "40px 20px" }}>
          <div className="empty-state-icon">📄</div>
          <div className="empty-state-title">No policies yet</div>
          <div className="empty-state-desc">Upload a policy document to start extracting rules.</div>
        </div>
      ) : (
        <div className="ws-list">
          {policies.map((p) => (
            <Link key={p.id} href={`/policy/${p.id}/rules`} className="card-link">
              <div className="card policy-card">
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 10, background: "#eff6ff",
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, flexShrink: 0,
                  }}>📋</div>
                  <div>
                    <div className="policy-card-title">
                      {p.title ?? "Untitled policy"}
                      <span style={{ fontSize: 11, fontWeight: 400, color: "var(--text-3)", marginLeft: 6 }}>v{p.version}</span>
                    </div>
                    <div className="policy-card-meta">
                      <span>{p.source_format}</span>
                      <span>·</span>
                      <span>{p.rule_count ?? 0} rules</span>
                      <span>·</span>
                      <span style={{ color: "#15803d" }}>{p.approved_rule_count ?? 0} approved</span>
                      {(p.open_ambiguity_count ?? 0) > 0 && (
                        <span className="badge badge-flag">⚑ {p.open_ambiguity_count} flag{(p.open_ambiguity_count ?? 0) > 1 ? "s" : ""}</span>
                      )}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 13, color: "var(--brand)", fontWeight: 500 }}>Review rules</span>
                  <span style={{ color: "var(--text-3)", fontSize: 18 }}>›</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
