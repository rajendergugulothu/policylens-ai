"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useApi, type Rule, type AmbiguityFlag, type Policy } from "@/lib/api";

const SEV_HEADER: Record<string, string> = {
  critical: "rule-card-header-critical",
  high:     "rule-card-header-high",
  medium:   "rule-card-header-medium",
  low:      "rule-card-header-low",
};

const SEV_BADGE: Record<string, string> = {
  critical: "badge-critical",
  high:     "badge-high",
  medium:   "badge-medium",
  low:      "badge-low",
};

const STATUS_BADGE: Record<string, string> = {
  pending_review:    "badge-pending",
  approved:          "badge-approved",
  rejected:          "badge-rejected",
  needs_resolution:  "badge-needs-resolution",
};

const STATUS_LABEL: Record<string, string> = {
  pending_review:   "Pending review",
  approved:         "Approved",
  rejected:         "Rejected",
  needs_resolution: "Needs resolution",
};

export default function RulesPage({ params }: { params: { id: string } }) {
  const api = useApi();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [flags, setFlags] = useState<AmbiguityFlag[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [extractMsg, setExtractMsg] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editBuf, setEditBuf] = useState<Partial<Rule>>({});
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolutionText, setResolutionText] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");

  const reload = async () => {
    const [r, f] = await Promise.all([
      api.rules.list(params.id),
      api.ambiguity.list(params.id),
    ]);
    setRules(r);
    setFlags(f);
  }

  useEffect(() => {
    api.policies.get(params.id).then(setPolicy);
    reload();
  }, [params.id]);

  async function handleExtract() {
    setExtracting(true);
    setExtractMsg("");
    try {
      const result = await api.rules.extract(params.id);
      setExtractMsg(result.message);
      await reload();
    } catch (e: unknown) {
      setExtractMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExtracting(false);
    }
  }

  async function handleApprove(ruleId: string) {
    if (!reviewer.trim()) { alert("Enter your name in the reviewer field first."); return; }
    await api.rules.approve(ruleId, reviewer);
    await reload();
  }

  async function handleEditSave(ruleId: string) {
    if (!reviewer.trim()) { alert("Enter your name in the reviewer field first."); return; }
    await api.rules.edit(ruleId, { ...editBuf, reviewed_by: reviewer });
    setEditingId(null);
    setEditBuf({});
    await reload();
  }

  async function handleReject(ruleId: string) {
    if (!reviewer.trim()) { alert("Enter your name in the reviewer field first."); return; }
    if (rejectNote.length < 10) { alert("Add a rejection reason (min 10 chars)."); return; }
    await api.rules.reject(ruleId, reviewer, rejectNote);
    setRejectingId(null);
    setRejectNote("");
    await reload();
  }

  async function handleResolve(flagId: string) {
    if (!reviewer.trim()) { alert("Enter your name in the reviewer field first."); return; }
    if (resolutionText.length < 20) { alert("Resolution must be at least 20 characters."); return; }
    await api.ambiguity.resolve(flagId, resolutionText, reviewer);
    setResolvingId(null);
    setResolutionText("");
    await reload();
  }

  const approved = rules.filter((r) => r.status === "approved").length;
  const critical = rules.filter((r) => r.status === "approved" && r.severity === "critical").length;
  const allApproved = rules.length > 0 && approved === rules.length && flags.length === 0;

  const filtered = filterStatus === "all" ? rules : rules.filter((r) => r.status === filterStatus);

  return (
    <div>
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <Link href="/">Workspaces</Link>
        <span>›</span>
        <Link href={`/workspace/${policy?.workspace_id ?? ""}`}>Workspace</Link>
        <span>›</span>
        <span>{policy?.title ?? "Policy"}</span>
      </div>

      {/* Page header */}
      <div className="page-header">
        <h1>
          {policy?.title ?? "Policy"}{" "}
          <span style={{ fontSize: 14, color: "var(--text-3)", fontWeight: 400 }}>v{policy?.version}</span>
        </h1>
        <p>Review and approve extracted policy rules before running compliance tests.</p>
      </div>

      {/* Stats */}
      <div className="stat-strip">
        {[
          { label: "Total rules", val: rules.length, color: "var(--text)" },
          { label: "Approved", val: approved, color: "#15803d" },
          { label: "Critical (approved)", val: critical, color: "#be123c" },
          { label: "Ambiguity flags", val: flags.length, color: flags.length ? "#b45309" : "var(--text-3)" },
        ].map(({ label, val, color }) => (
          <div key={label} className="stat-card">
            <div className="stat-label">{label}</div>
            <div className="stat-value" style={{ color }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Ready banner */}
      {allApproved && (
        <div className="alert alert-success">
          <span>✓</span>
          <span>All {approved} rules approved with no open ambiguity flags — ready to generate test scenarios.</span>
        </div>
      )}

      {/* Extract button */}
      {rules.length === 0 && (
        <div className="card" style={{ padding: "32px 24px", textAlign: "center", marginBottom: 24 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🤖</div>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>No rules extracted yet</div>
          <div style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 20 }}>
            PolicyLens will call Claude to extract structured, testable rules from the policy document.
          </div>
          <button onClick={handleExtract} disabled={extracting} className="btn btn-primary">
            {extracting ? "Extracting rules with Claude…" : "Extract rules with Claude"}
          </button>
          {extractMsg && (
            <p style={{ fontSize: 13, color: "var(--text-2)", marginTop: 14 }}>{extractMsg}</p>
          )}
        </div>
      )}

      {/* Reviewer + filter toolbar */}
      {rules.length > 0 && (
        <div className="toolbar">
          <span className="toolbar-label">Reviewing as:</span>
          <input
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            placeholder="your.name@company.com"
            className="input"
            style={{ width: 220 }}
          />
          <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
            {["all", "pending_review", "approved", "rejected", "needs_resolution"].map((s) => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className="btn btn-ghost btn-sm"
                style={{
                  borderColor: filterStatus === s ? "var(--brand)" : undefined,
                  color: filterStatus === s ? "var(--brand)" : undefined,
                  fontWeight: filterStatus === s ? 600 : 400,
                }}
              >
                {s === "all" ? "All" : STATUS_LABEL[s] ?? s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Ambiguity flags */}
      {flags.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div className="section-header" style={{ color: "#b45309" }}>
            ⚑ Ambiguity flags — resolve before scenario generation ({flags.length})
          </div>
          <div className="alert alert-warning" style={{ marginBottom: 12 }}>
            Scenario generation is blocked until all ambiguity flags are resolved in writing.
          </div>
          {flags.map((flag) => (
            <div key={flag.id} className="flag-card">
              <div style={{ fontSize: 12, fontWeight: 600, color: "#78350f", marginBottom: 8 }}>
                Ambiguous clause
              </div>
              <div className="flag-clause">"{flag.flagged_clause}"</div>
              <div className="flag-reason">
                <strong>Why flagged:</strong> {flag.flag_reason}
              </div>
              {resolvingId === flag.id ? (
                <div>
                  <label className="field-label">Resolution (plain language)</label>
                  <textarea
                    value={resolutionText}
                    onChange={(e) => setResolutionText(e.target.value)}
                    placeholder="Write the intended behavior in plain language (min 20 chars)…"
                    rows={3}
                    className="textarea"
                    style={{ marginBottom: 10, fontSize: 13 }}
                  />
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => handleResolve(flag.id)} className="btn btn-success btn-sm">Submit resolution</button>
                    <button onClick={() => setResolvingId(null)} className="btn btn-ghost btn-sm">Cancel</button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setResolvingId(flag.id)} className="btn btn-sm" style={{ background: "#b45309", color: "#fff" }}>
                  Write resolution
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Rules list */}
      {filtered.length > 0 && (
        <div>
          <div className="section-header">
            Extracted rules — {filtered.length}{filterStatus !== "all" ? ` ${STATUS_LABEL[filterStatus] ?? filterStatus}` : ""} of {rules.length}
          </div>
          {filtered.map((rule) => (
            <div key={rule.id} className="card rule-card">
              {/* Rule header */}
              <div className={`rule-card-header ${SEV_HEADER[rule.severity] ?? ""}`}>
                <div className="rule-meta-row">
                  <span className="rule-card-id">{rule.rule_number}</span>
                  <span className={`badge ${SEV_BADGE[rule.severity] ?? ""}`}>{rule.severity}</span>
                  <span className={`badge ${STATUS_BADGE[rule.status] ?? "badge-pending"}`}>
                    {STATUS_LABEL[rule.status] ?? rule.status}
                  </span>
                  {rule.has_open_ambiguity && (
                    <span className="badge badge-flag">⚑ ambiguity flag</span>
                  )}
                </div>
                {rule.source_section && (
                  <a
                    href={rule.source_citation_url ?? "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="source-link"
                  >
                    {rule.source_section}{rule.source_page ? ` p.${rule.source_page}` : ""} ↗
                  </a>
                )}
              </div>

              {/* Rule body */}
              <div className="rule-card-body">
                {editingId === rule.id ? (
                  <div>
                    <label className="field-label">Condition</label>
                    <textarea
                      defaultValue={rule.condition}
                      onChange={(e) => setEditBuf((b) => ({ ...b, condition: e.target.value }))}
                      rows={2}
                      className="textarea"
                      style={{ marginBottom: 10, fontSize: 13 }}
                    />
                    <label className="field-label">Action</label>
                    <textarea
                      defaultValue={rule.action}
                      onChange={(e) => setEditBuf((b) => ({ ...b, action: e.target.value }))}
                      rows={2}
                      className="textarea"
                      style={{ marginBottom: 12, fontSize: 13 }}
                    />
                    <div className="rule-actions">
                      <button onClick={() => handleEditSave(rule.id)} className="btn btn-success btn-sm">Save and approve</button>
                      <button onClick={() => { setEditingId(null); setEditBuf({}); }} className="btn btn-ghost btn-sm">Cancel</button>
                    </div>
                  </div>
                ) : rejectingId === rule.id ? (
                  <div>
                    <label className="field-label">Rejection reason</label>
                    <textarea
                      value={rejectNote}
                      onChange={(e) => setRejectNote(e.target.value)}
                      placeholder="Explain why this rule is incorrect or a duplicate (min 10 chars)…"
                      rows={2}
                      className="textarea"
                      style={{ marginBottom: 10, fontSize: 13, borderColor: "#fca5a5" }}
                    />
                    <div className="rule-actions">
                      <button onClick={() => handleReject(rule.id)} className="btn btn-danger btn-sm">Confirm reject</button>
                      <button onClick={() => { setRejectingId(null); setRejectNote(""); }} className="btn btn-ghost btn-sm">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="rule-if">
                      <strong>IF</strong>
                      {rule.condition}
                    </div>
                    <div className="rule-if">
                      <strong>THEN</strong>
                      {rule.action}
                    </div>
                    {rule.exception && (
                      <div className="rule-exception">Exception: {rule.exception}</div>
                    )}
                    {rule.notes && (
                      <div className="rule-citation">{rule.notes.substring(0, 200)}</div>
                    )}

                    {rule.status === "approved" ? (
                      <div className="rule-approved-by">
                        <span style={{ color: "#22c55e" }}>✓</span>
                        Approved by {rule.reviewed_by}
                      </div>
                    ) : rule.status === "rejected" ? (
                      <div style={{ fontSize: 12, color: "var(--red-text)", marginTop: 10 }}>
                        ✗ Rejected by {rule.reviewed_by}
                      </div>
                    ) : (
                      <div className="rule-actions">
                        <button
                          onClick={() => handleApprove(rule.id)}
                          disabled={rule.has_open_ambiguity}
                          className="btn btn-success btn-sm"
                          title={rule.has_open_ambiguity ? "Resolve ambiguity flag first" : ""}
                        >
                          ✓ Approve
                        </button>
                        <button
                          onClick={() => { setEditingId(rule.id); setEditBuf({ condition: rule.condition, action: rule.action }); }}
                          className="btn btn-ghost btn-sm"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => setRejectingId(rule.id)}
                          className="btn btn-ghost btn-sm"
                          style={{ color: "var(--red-text)", borderColor: "#fca5a5" }}
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
