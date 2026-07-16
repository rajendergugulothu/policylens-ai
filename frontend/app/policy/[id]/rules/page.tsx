"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Rule, type AmbiguityFlag, type Policy } from "@/lib/api";

const SEV_COLORS: Record<string, string> = {
  critical: "#fef2f2",
  high: "#fffbeb",
  medium: "#f0fdf4",
  low: "#f9fafb",
};
const SEV_TEXT: Record<string, string> = {
  critical: "#991b1b",
  high: "#92400e",
  medium: "#166534",
  low: "#6b7280",
};
const STATUS_LABEL: Record<string, string> = {
  pending_review: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  needs_resolution: "Needs resolution",
};
const STATUS_COLOR: Record<string, string> = {
  pending_review: "#1e3a8a",
  approved: "#166534",
  rejected: "#991b1b",
  needs_resolution: "#92400e",
};

export default function RulesPage({ params }: { params: { id: string } }) {
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

  async function reload() {
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

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Link href={`/workspace/${policy?.workspace_id ?? ""}`} style={{ color: "#1e3a8a", fontSize: 13 }}>← Workspace</Link>
      </div>
      <h1 style={{ fontSize: 20, fontWeight: 500, marginBottom: 4 }}>
        {policy?.title ?? "Policy"} <span style={{ fontSize: 13, color: "#9ca3af", fontWeight: 400 }}>v{policy?.version}</span>
      </h1>

      {/* Stats bar */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Rules", val: rules.length, color: "#1e3a8a" },
          { label: "Approved", val: approved, color: "#166534" },
          { label: "Critical (approved)", val: critical, color: "#991b1b" },
          { label: "Ambiguity flags", val: flags.length, color: flags.length ? "#92400e" : "#9ca3af" },
        ].map(({ label, val, color }) => (
          <div key={label} style={{ background: "#fff", border: "0.5px solid #e5e7eb", borderRadius: 8, padding: "8px 14px", minWidth: 100 }}>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 20, fontWeight: 500, color }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Reviewer field */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 20 }}>
        <span style={{ fontSize: 13, color: "#6b7280", whiteSpace: "nowrap" }}>Reviewing as:</span>
        <input
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          placeholder="your.name@company.com"
          style={{ padding: "6px 10px", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 13, width: 240 }}
        />
      </div>

      {/* Extract button */}
      {rules.length === 0 && (
        <div style={{ marginBottom: 24 }}>
          <button
            onClick={handleExtract}
            disabled={extracting}
            style={{ padding: "9px 20px", background: "#1e3a8a", color: "#fff", border: "none", borderRadius: 8, fontSize: 14, cursor: "pointer", opacity: extracting ? 0.6 : 1 }}
          >
            {extracting ? "Extracting rules…" : "Extract rules with Claude"}
          </button>
          {extractMsg && <p style={{ fontSize: 13, color: "#374151", marginTop: 8 }}>{extractMsg}</p>}
        </div>
      )}

      {/* Ready banner */}
      {allApproved && (
        <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "12px 16px", marginBottom: 20, fontSize: 14, color: "#166534" }}>
          All {approved} rules approved with no open ambiguity flags. Ready to generate scenarios.
        </div>
      )}

      {/* Ambiguity flags */}
      {flags.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 500, color: "#92400e", marginBottom: 10 }}>
            Ambiguity flags — resolve before testing ({flags.length})
          </h2>
          <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
            Scenario generation is blocked until all flags are resolved in writing.
          </p>
          {flags.map((flag) => (
            <div key={flag.id} style={{ background: "#fffbeb", border: "0.5px solid #fde68a", borderRadius: 10, padding: "14px 16px", marginBottom: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: "#78350f", marginBottom: 4 }}>
                Ambiguous clause
              </div>
              <div style={{ fontSize: 12, fontStyle: "italic", color: "#92400e", marginBottom: 6, borderLeft: "2px solid #f59e0b", paddingLeft: 8 }}>
                "{flag.flagged_clause}"
              </div>
              <div style={{ fontSize: 12, color: "#78350f", marginBottom: 10 }}>
                Why flagged: {flag.flag_reason}
              </div>
              {resolvingId === flag.id ? (
                <div>
                  <textarea
                    value={resolutionText}
                    onChange={(e) => setResolutionText(e.target.value)}
                    placeholder="Write the intended behavior in plain language (min 20 chars)…"
                    rows={3}
                    style={{ width: "100%", padding: "8px 10px", border: "0.5px solid #fcd34d", borderRadius: 6, fontSize: 12, boxSizing: "border-box", marginBottom: 8 }}
                  />
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => handleResolve(flag.id)} style={{ padding: "6px 14px", background: "#166534", color: "#fff", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
                      Submit resolution
                    </button>
                    <button onClick={() => setResolvingId(null)} style={{ padding: "6px 14px", background: "transparent", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setResolvingId(flag.id)} style={{ padding: "6px 14px", background: "#92400e", color: "#fff", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
                  Write resolution
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Rules table */}
      {rules.length > 0 && (
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 500, marginBottom: 10 }}>Extracted rules ({rules.length})</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {rules.map((rule) => (
              <div key={rule.id} style={{ background: "#fff", border: "0.5px solid #e5e7eb", borderRadius: 10, overflow: "hidden" }}>
                <div style={{ background: SEV_COLORS[rule.severity] ?? "#f9fafb", padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "0.5px solid #e5e7eb" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{rule.rule_number}</span>
                    <span style={{ fontSize: 11, fontWeight: 500, color: SEV_TEXT[rule.severity] ?? "#6b7280", background: "#fff", padding: "2px 8px", borderRadius: 10, border: "0.5px solid #e5e7eb" }}>
                      {rule.severity}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 500, color: STATUS_COLOR[rule.status] ?? "#6b7280" }}>
                      {STATUS_LABEL[rule.status] ?? rule.status}
                    </span>
                    {rule.has_open_ambiguity && (
                      <span style={{ fontSize: 11, background: "#fef3c7", color: "#92400e", padding: "2px 8px", borderRadius: 10 }}>
                        ambiguity flag
                      </span>
                    )}
                  </div>
                  {rule.source_section && (
                    <a
                      href={rule.source_citation_url ?? "#"}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: 11, color: "#1e3a8a", textDecoration: "none" }}
                    >
                      {rule.source_section}{rule.source_page ? ` p.${rule.source_page}` : ""} ↗
                    </a>
                  )}
                </div>

                <div style={{ padding: "12px 14px" }}>
                  {editingId === rule.id ? (
                    <div>
                      <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 4 }}>Condition</label>
                      <textarea
                        defaultValue={rule.condition}
                        onChange={(e) => setEditBuf((b) => ({ ...b, condition: e.target.value }))}
                        rows={2}
                        style={{ width: "100%", padding: "6px 8px", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 13, boxSizing: "border-box", marginBottom: 8 }}
                      />
                      <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 4 }}>Action</label>
                      <textarea
                        defaultValue={rule.action}
                        onChange={(e) => setEditBuf((b) => ({ ...b, action: e.target.value }))}
                        rows={2}
                        style={{ width: "100%", padding: "6px 8px", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 13, boxSizing: "border-box", marginBottom: 8 }}
                      />
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={() => handleEditSave(rule.id)} style={{ padding: "6px 14px", background: "#166534", color: "#fff", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>Save and approve</button>
                        <button onClick={() => { setEditingId(null); setEditBuf({}); }} style={{ padding: "6px 12px", background: "transparent", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>Cancel</button>
                      </div>
                    </div>
                  ) : rejectingId === rule.id ? (
                    <div>
                      <textarea
                        value={rejectNote}
                        onChange={(e) => setRejectNote(e.target.value)}
                        placeholder="Rejection reason (min 10 chars)…"
                        rows={2}
                        style={{ width: "100%", padding: "6px 8px", border: "0.5px solid #fca5a5", borderRadius: 6, fontSize: 12, boxSizing: "border-box", marginBottom: 8 }}
                      />
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={() => handleReject(rule.id)} style={{ padding: "6px 14px", background: "#991b1b", color: "#fff", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>Confirm reject</button>
                        <button onClick={() => { setRejectingId(null); setRejectNote(""); }} style={{ padding: "6px 12px", background: "transparent", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        <strong>If:</strong> {rule.condition}
                      </div>
                      <div style={{ fontSize: 13, marginBottom: rule.exception ? 6 : 0 }}>
                        <strong>Then:</strong> {rule.action}
                      </div>
                      {rule.exception && (
                        <div style={{ fontSize: 12, color: "#6b7280", fontStyle: "italic", marginBottom: 6 }}>
                          Exception: {rule.exception}
                        </div>
                      )}
                      {rule.notes && (
                        <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4, borderLeft: "2px solid #e5e7eb", paddingLeft: 6 }}>
                          {rule.notes.substring(0, 200)}
                        </div>
                      )}
                      {rule.status !== "approved" && rule.status !== "rejected" && (
                        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                          <button
                            onClick={() => handleApprove(rule.id)}
                            disabled={rule.has_open_ambiguity}
                            style={{ padding: "5px 14px", background: "#166534", color: "#fff", border: "none", borderRadius: 6, fontSize: 12, cursor: rule.has_open_ambiguity ? "not-allowed" : "pointer", opacity: rule.has_open_ambiguity ? 0.5 : 1 }}
                          >
                            Approve
                          </button>
                          <button onClick={() => { setEditingId(rule.id); setEditBuf({ condition: rule.condition, action: rule.action }); }} style={{ padding: "5px 12px", background: "transparent", border: "0.5px solid #d1d5db", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
                            Edit
                          </button>
                          <button onClick={() => setRejectingId(rule.id)} style={{ padding: "5px 12px", background: "transparent", border: "0.5px solid #fca5a5", borderRadius: 6, fontSize: 12, cursor: "pointer", color: "#991b1b" }}>
                            Reject
                          </button>
                        </div>
                      )}
                      {rule.status === "approved" && (
                        <div style={{ fontSize: 12, color: "#166534", marginTop: 8 }}>
                          Approved by {rule.reviewed_by}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
