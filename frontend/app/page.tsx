"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useApi, type Workspace } from "@/lib/api";

export default function Home() {
  const api = useApi();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.workspaces.list().then(setWorkspaces).finally(() => setLoading(false));
  }, []);

  async function handleCreate() {
    if (!name.trim()) return;
    setCreating(true);
    const ws = await api.workspaces.create(name.trim());
    setWorkspaces((prev) => [ws, ...prev]);
    setName("");
    setCreating(false);
  }

  return (
    <div>
      {/* Page header */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
        <div>
          <h1>Workspaces</h1>
          <p>Each workspace tests one AI agent workflow against one policy document.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. ShopFast Returns Agent v3"
            className="input"
            style={{ width: 280 }}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <button
            onClick={handleCreate}
            disabled={creating || !name.trim()}
            className="btn btn-primary"
          >
            {creating ? "Creating…" : "+ New workspace"}
          </button>
        </div>
      </div>

      {/* Stats row */}
      {!loading && workspaces.length > 0 && (
        <div className="stat-strip">
          {[
            { label: "Total workspaces", val: workspaces.length, color: "var(--brand)" },
            { label: "Refund workflows", val: workspaces.filter(w => w.workflow_type === "refund").length, color: "#15803d" },
            { label: "Sandbox mode", val: workspaces.filter(w => w.is_sandbox).length, color: "#b45309" },
          ].map(({ label, val, color }) => (
            <div key={label} className="stat-card">
              <div className="stat-label">{label}</div>
              <div className="stat-value" style={{ color }}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Workspace list */}
      {loading ? (
        <div className="empty-state">
          <div className="empty-state-desc">Loading workspaces…</div>
        </div>
      ) : workspaces.length === 0 ? (
        <div className="empty-state card" style={{ padding: "48px 20px" }}>
          <div className="empty-state-icon">🏗️</div>
          <div className="empty-state-title">No workspaces yet</div>
          <div className="empty-state-desc">Create a workspace to start testing an AI agent against a policy.</div>
        </div>
      ) : (
        <div className="ws-list">
          {workspaces.map((ws) => (
            <Link key={ws.id} href={`/workspace/${ws.id}`} className="card-link">
              <div className="card ws-card">
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 10,
                    background: "var(--brand-light)", display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 18, flexShrink: 0,
                  }}>🏢</div>
                  <div>
                    <div className="ws-card-title">{ws.name}</div>
                    <div className="ws-card-meta">
                      <span className={`badge badge-${ws.workflow_type === "refund" ? "approved" : "pending"}`}>{ws.workflow_type}</span>
                      <span>·</span>
                      <span>{ws.policy_count ?? 0} polic{(ws.policy_count ?? 0) === 1 ? "y" : "ies"}</span>
                      {ws.is_sandbox && <><span>·</span><span style={{ color: "#b45309" }}>sandbox</span></>}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <div className="ws-card-date">{new Date(ws.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</div>
                  <div className="ws-card-arrow">›</div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
