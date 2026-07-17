"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useApi, type EvaluationRun, type Finding, type Release } from "@/lib/api";

const SEV_BADGE: Record<string, string> = {
  critical: "badge-critical",
  major: "badge-high",
  minor: "badge-medium",
};

const ROLES = ["qa_lead", "vp_operations", "compliance_officer", "head_of_ai"];

export default function EvaluationPage({ params }: { params: { id: string } }) {
  const api = useApi();
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [release, setRelease] = useState<Release | null>(null);
  const [polling, setPolling] = useState(false);
  const [buildingRelease, setBuildingRelease] = useState(false);
  const [signerName, setSignerName] = useState("");
  const [signerRole, setSignerRole] = useState("qa_lead");
  const [signing, setSigning] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const load = useCallback(async () => {
    const r = await api.evaluations.get(params.id);
    setRun(r);
    if (r.status === "completed") {
      const f = await api.evaluations.findings(params.id);
      setFindings(f);
    }
    return r;
  }, [params.id]);

  useEffect(() => {
    load().then((r) => {
      if (r.status === "pending" || r.status === "running") {
        setPolling(true);
      }
    });
  }, [load]);

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(async () => {
      const r = await load();
      if (r.status === "completed" || r.status === "failed") {
        setPolling(false);
        clearInterval(interval);
      }
    }, 4000);
    return () => clearInterval(interval);
  }, [polling, load]);

  async function handleBuildRelease() {
    if (!run) return;
    setBuildingRelease(true);
    setMsg(null);
    try {
      const rel = await api.releases.create(run.id);
      setRelease(rel);
      setMsg({ text: "Launch-readiness report built successfully.", ok: true });
    } catch (e: unknown) {
      setMsg({ text: `Error: ${e instanceof Error ? e.message : String(e)}`, ok: false });
    } finally {
      setBuildingRelease(false);
    }
  }

  async function handleSign() {
    if (!release || !signerName.trim()) return;
    setSigning(true);
    try {
      const updated = await api.releases.sign(release.id, signerName.trim(), signerRole);
      setRelease(updated);
      setSignerName("");
      setMsg({ text: `Signed by ${signerName}. ${updated.signatures.length}/2 signatures collected.`, ok: true });
    } catch (e: unknown) {
      setMsg({ text: `Error: ${e instanceof Error ? e.message : String(e)}`, ok: false });
    } finally {
      setSigning(false);
    }
  }

  const critical = findings.filter((f) => f.severity === "critical");
  const major = findings.filter((f) => f.severity === "major");
  const minor = findings.filter((f) => f.severity === "minor");

  const recColor = release?.recommendation === "ready" ? "#15803d"
    : release?.recommendation === "conditionally_ready" ? "#b45309" : "#be123c";
  const recLabel = release?.recommendation === "ready" ? "✓ READY TO LAUNCH"
    : release?.recommendation === "conditionally_ready" ? "⚠ CONDITIONALLY READY"
    : "✗ NOT READY — DO NOT LAUNCH";

  return (
    <div>
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <Link href="/">Workspaces</Link>
        <span>›</span>
        <Link href={`/workspace/${run?.workspace_id ?? ""}`}>Workspace</Link>
        <span>›</span>
        <span>Evaluation Run</span>
      </div>

      {/* Page header */}
      <div className="page-header">
        <h1>Evaluation Run</h1>
        <p style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {run?.version_label && <span className="badge badge-pending">{run.version_label}</span>}
          <span>{run?.agent_endpoint_url}</span>
        </p>
      </div>

      {/* Status + stats */}
      <div className="stat-strip">
        {[
          { label: "Status", val: run?.status ?? "…", color: run?.status === "completed" ? "#15803d" : run?.status === "failed" ? "#be123c" : "#b45309" },
          { label: "Total scenarios", val: run?.total_scenarios ?? 0, color: "var(--text)" },
          { label: "Passed", val: run?.passed ?? 0, color: "#15803d" },
          { label: "Failed", val: run?.failed ?? 0, color: "#be123c" },
          { label: "Critical violations", val: run?.critical_violations ?? 0, color: "#be123c" },
          { label: "Decision accuracy", val: run?.decision_accuracy_pct != null ? `${run.decision_accuracy_pct.toFixed(1)}%` : "—", color: (run?.decision_accuracy_pct ?? 0) >= 90 ? "#15803d" : "#be123c" },
        ].map(({ label, val, color }) => (
          <div key={label} className="stat-card">
            <div className="stat-label">{label}</div>
            <div className="stat-value" style={{ color, fontSize: typeof val === "string" && val.length > 4 ? 18 : 26 }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Polling banner */}
      {polling && (
        <div className="alert alert-info" style={{ marginBottom: 20 }}>
          <span>⏳</span>
          <span>Evaluation is running — PolicyLens is calling your agent for each scenario. Auto-refreshing every 4 seconds…</span>
        </div>
      )}

      {/* Flash */}
      {msg && (
        <div className={`alert ${msg.ok ? "alert-success" : "alert-error"}`} style={{ marginBottom: 20 }}>
          {msg.ok ? "✓" : "✗"} {msg.text}
        </div>
      )}

      {/* Findings */}
      {run?.status === "completed" && findings.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          <div className="section-header">
            Policy violations found — {findings.length} total
          </div>

          {/* Critical */}
          {critical.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#be123c", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>
                Critical ({critical.length}) — must fix before launch
              </div>
              {critical.map((f) => <FindingCard key={f.id} finding={f} />)}
            </div>
          )}

          {/* Major */}
          {major.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#b45309", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>
                Major ({major.length})
              </div>
              {major.map((f) => <FindingCard key={f.id} finding={f} />)}
            </div>
          )}

          {/* Minor */}
          {minor.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>
                Minor ({minor.length})
              </div>
              {minor.map((f) => <FindingCard key={f.id} finding={f} />)}
            </div>
          )}
        </div>
      )}

      {/* No violations */}
      {run?.status === "completed" && findings.length === 0 && (
        <div className="alert alert-success" style={{ marginBottom: 32 }}>
          ✓ No policy violations found. Agent passed all scenarios.
        </div>
      )}

      {/* Build release report */}
      {run?.status === "completed" && !release && (
        <div className="card" style={{ padding: "24px", marginBottom: 24 }}>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>Build launch-readiness report</div>
          <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 16 }}>
            Computes recommendation (ready / conditionally ready / not ready), decision accuracy, critical violation rate, and scenario coverage.
          </div>
          <button onClick={handleBuildRelease} disabled={buildingRelease} className="btn btn-primary">
            {buildingRelease ? "Building report…" : "Build report"}
          </button>
        </div>
      )}

      {/* Release report */}
      {release && (
        <div className="card" style={{ padding: "24px", marginBottom: 24 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 16 }}>
            Launch-Readiness Report
          </div>

          {/* Recommendation */}
          <div style={{
            padding: "14px 18px", borderRadius: 10, marginBottom: 20,
            background: release.recommendation === "ready" ? "#f0fdf4" : release.recommendation === "conditionally_ready" ? "#fffbeb" : "#fff1f2",
            border: `1px solid ${release.recommendation === "ready" ? "#bbf7d0" : release.recommendation === "conditionally_ready" ? "#fde68a" : "#fecdd3"}`,
          }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: recColor, marginBottom: 4 }}>{recLabel}</div>
            {release.recommendation_reason && (
              <div style={{ fontSize: 13, color: recColor, opacity: .8 }}>{release.recommendation_reason}</div>
            )}
          </div>

          {/* Metrics */}
          <div className="stat-strip" style={{ marginBottom: 20 }}>
            {[
              { label: "Decision accuracy", val: release.decision_accuracy_pct != null ? `${release.decision_accuracy_pct.toFixed(1)}%` : "—", color: (release.decision_accuracy_pct ?? 0) >= 90 ? "#15803d" : "#be123c" },
              { label: "Critical violation rate", val: release.critical_violation_rate != null ? `${release.critical_violation_rate.toFixed(1)}%` : "—", color: (release.critical_violation_rate ?? 1) === 0 ? "#15803d" : "#be123c" },
              { label: "Scenario coverage", val: release.scenario_coverage_pct != null ? `${release.scenario_coverage_pct.toFixed(1)}%` : "—", color: "#15803d" },
              { label: "Open findings", val: release.open_findings, color: release.open_findings === 0 ? "#15803d" : "#be123c" },
            ].map(({ label, val, color }) => (
              <div key={label} className="stat-card">
                <div className="stat-label">{label}</div>
                <div className="stat-value" style={{ color, fontSize: 20 }}>{val}</div>
              </div>
            ))}
          </div>

          {/* Signatures */}
          <div style={{ marginBottom: 16 }}>
            <div className="section-header">Dual sign-off ({release.signatures.length}/2)</div>
            {release.signatures.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                {release.signatures.map((s, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ color: "#22c55e" }}>✓</span>
                    <span style={{ fontWeight: 500 }}>{s.signer_name}</span>
                    <span className="badge badge-pending">{s.signer_role}</span>
                    <span style={{ color: "var(--text-3)", fontSize: 12, marginLeft: "auto" }}>{new Date(s.signed_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}

            {release.status !== "approved" && release.signatures.length < 2 && (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
                <div>
                  <label className="field-label">Your name</label>
                  <input value={signerName} onChange={(e) => setSignerName(e.target.value)} placeholder="e.g. Sarah Chen" className="input" style={{ width: 200 }} />
                </div>
                <div>
                  <label className="field-label">Role</label>
                  <select value={signerRole} onChange={(e) => setSignerRole(e.target.value)} className="input" style={{ width: 180 }}>
                    {ROLES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
                  </select>
                </div>
                <button onClick={handleSign} disabled={signing || !signerName.trim()} className="btn btn-success">
                  {signing ? "Signing…" : "Sign release"}
                </button>
              </div>
            )}

            {release.status === "approved" && (
              <div className="alert alert-success" style={{ marginTop: 12 }}>
                ✓ Release approved — dual sign-off complete.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <div className="card" style={{ padding: "14px 16px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span className={`badge ${SEV_BADGE[finding.severity] ?? "badge-medium"}`} style={{ flexShrink: 0, marginTop: 2 }}>
          {finding.severity}
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{finding.scenario_title}</div>
          {finding.violated_clause && (
            <div style={{ fontSize: 12, color: "var(--text-3)", borderLeft: "3px solid var(--border)", paddingLeft: 8, marginBottom: 4 }}>
              {finding.violated_clause.substring(0, 160)}…
            </div>
          )}
          <div style={{ display: "flex", gap: 12, fontSize: 12, color: "var(--text-3)" }}>
            {finding.expected_action && <span>Expected: <strong style={{ color: "var(--text-2)" }}>{finding.expected_action}</strong></span>}
            {finding.agent_action && <span>Agent: <strong style={{ color: "#be123c" }}>{finding.agent_action}</strong></span>}
            {finding.likely_cause && <span className="badge badge-flag">{finding.likely_cause}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
