"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Workspace } from "@/lib/api";

export default function Home() {
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
      <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 4 }}>Workspaces</h1>
      <p style={{ color: "#6b7280", marginBottom: 24, fontSize: 14 }}>
        Each workspace tests one AI agent workflow against one policy.
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 32 }}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. ShopFast Returns Agent v3"
          style={{ flex: 1, padding: "8px 12px", border: "0.5px solid #d1d5db", borderRadius: 8, fontSize: 14 }}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
        />
        <button
          onClick={handleCreate}
          disabled={creating || !name.trim()}
          style={{ padding: "8px 18px", background: "#1e3a8a", color: "#fff", border: "none", borderRadius: 8, fontSize: 14, cursor: "pointer", opacity: creating ? 0.6 : 1 }}
        >
          {creating ? "Creating…" : "New workspace"}
        </button>
      </div>

      {loading ? (
        <p style={{ color: "#9ca3af" }}>Loading…</p>
      ) : workspaces.length === 0 ? (
        <p style={{ color: "#9ca3af", fontSize: 14 }}>No workspaces yet. Create one above.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {workspaces.map((ws) => (
            <Link
              key={ws.id}
              href={`/workspace/${ws.id}`}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div style={{ background: "#fff", border: "0.5px solid #e5e7eb", borderRadius: 10, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}>
                <div>
                  <div style={{ fontWeight: 500, marginBottom: 2 }}>{ws.name}</div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>{ws.workflow_type} · {ws.policy_count} polic{ws.policy_count === 1 ? "y" : "ies"}</div>
                </div>
                <div style={{ fontSize: 12, color: "#9ca3af" }}>
                  {new Date(ws.created_at).toLocaleDateString()}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
