const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface Workspace {
  id: string;
  name: string;
  workflow_type: string;
  is_sandbox: boolean;
  created_by: string | null;
  created_at: string;
  policy_count: number;
}

export interface Policy {
  id: string;
  workspace_id: string;
  version: number;
  title: string | null;
  source_format: string;
  source_url: string | null;
  page_count: number | null;
  is_active: boolean;
  created_at: string;
  rule_count: number;
  approved_rule_count: number;
  open_ambiguity_count: number;
}

export interface Rule {
  id: string;
  policy_id: string;
  rule_number: string;
  condition: string;
  action: string;
  exception: string | null;
  required_evidence: string | null;
  source_section: string | null;
  source_page: number | null;
  source_citation_url: string | null;
  notes: string | null;
  severity: "critical" | "high" | "medium" | "low";
  status: "pending_review" | "approved" | "rejected" | "needs_resolution";
  reviewed_by: string | null;
  has_open_ambiguity: boolean;
}

export interface EvaluationRun {
  id: string;
  workspace_id: string;
  policy_id: string;
  version_label: string | null;
  agent_type: string;
  agent_endpoint_url: string | null;
  status: "pending" | "running" | "completed" | "failed";
  total_scenarios: number;
  passed: number;
  failed: number;
  critical_violations: number;
  decision_accuracy_pct: number | null;
  started_at: string;
  completed_at: string | null;
  created_by: string | null;
}

export interface Finding {
  id: string;
  evaluation_run_id: string;
  scenario_id: string;
  scenario_title: string;
  rule_id: string | null;
  violated_clause: string | null;
  severity: "critical" | "major" | "minor";
  likely_cause: string | null;
  agent_action: string | null;
  expected_action: string | null;
  status: string;
}

export interface Release {
  id: string;
  workspace_id: string;
  evaluation_run_id: string;
  recommendation: string;
  recommendation_reason: string | null;
  critical_violation_rate: number | null;
  decision_accuracy_pct: number | null;
  scenario_coverage_pct: number | null;
  open_findings: number;
  status: string;
  signatures: { signer_name: string; signer_role: string; signed_at: string }[];
}

export interface AmbiguityFlag {
  id: string;
  rule_id: string;
  flagged_clause: string;
  flag_reason: string;
  resolution: string | null;
  resolved_by: string | null;
  status: "open" | "resolved";
}

export interface ExtractionResponse {
  policy_id: string;
  rules_extracted: number;
  ambiguity_flags_created: number;
  rules_needing_review: number;
  message: string;
}

// ── Workspace API ─────────────────────────────────────────────────────────

export const api = {
  workspaces: {
    list: () => request<Workspace[]>("/workspaces/"),
    get: (id: string) => request<Workspace>(`/workspaces/${id}`),
    create: (name: string, workflowType = "refund") =>
      request<Workspace>("/workspaces/", {
        method: "POST",
        body: JSON.stringify({ name, workflow_type: workflowType }),
      }),
  },

  policies: {
    list: (workspaceId: string) =>
      request<Policy[]>(`/policies/workspace/${workspaceId}`),
    get: (id: string) => request<Policy>(`/policies/${id}`),
    uploadText: (workspaceId: string, rawText: string, title?: string) => {
      const form = new FormData();
      form.append("workspace_id", workspaceId);
      form.append("raw_text", rawText);
      if (title) form.append("title", title);
      return fetch(`${API_BASE}/policies/upload/text`, { method: "POST", body: form })
        .then((r) => r.json());
    },
  },

  rules: {
    extract: (policyId: string) =>
      request<ExtractionResponse>(`/rules/extract/${policyId}`, { method: "POST" }),
    list: (policyId: string) =>
      request<Rule[]>(`/rules/policy/${policyId}`),
    approve: (ruleId: string, reviewedBy: string) =>
      request<Rule>(`/rules/${ruleId}/approve`, {
        method: "POST",
        body: JSON.stringify({ reviewed_by: reviewedBy }),
      }),
    edit: (ruleId: string, edits: Partial<Rule> & { reviewed_by: string }) =>
      request<Rule>(`/rules/${ruleId}/edit`, {
        method: "POST",
        body: JSON.stringify(edits),
      }),
    reject: (ruleId: string, reviewedBy: string, notes: string) =>
      request<Rule>(`/rules/${ruleId}/reject`, {
        method: "POST",
        body: JSON.stringify({ reviewed_by: reviewedBy, notes }),
      }),
  },

  evaluations: {
    list: (workspaceId: string) =>
      request<EvaluationRun[]>(`/evaluations/workspace/${workspaceId}`),
    get: (id: string) => request<EvaluationRun>(`/evaluations/${id}`),
    create: (payload: {
      policy_id: string;
      agent_endpoint_url: string;
      version_label?: string;
      created_by?: string;
    }) =>
      request<EvaluationRun>("/evaluations/", {
        method: "POST",
        body: JSON.stringify({ agent_type: "endpoint", ...payload }),
      }),
    findings: (id: string) => request<Finding[]>(`/evaluations/${id}/findings`),
  },

  releases: {
    create: (evaluationRunId: string, createdBy?: string) =>
      request<Release>("/releases/", {
        method: "POST",
        body: JSON.stringify({ evaluation_run_id: evaluationRunId, created_by: createdBy ?? "ui-user" }),
      }),
    get: (id: string) => request<Release>(`/releases/${id}`),
    sign: (id: string, signerName: string, signerRole: string) =>
      request<Release>(`/releases/${id}/sign`, {
        method: "POST",
        body: JSON.stringify({ signer_name: signerName, signer_role: signerRole }),
      }),
  },

  ambiguity: {
    list: (policyId: string) =>
      request<AmbiguityFlag[]>(`/rules/ambiguity/policy/${policyId}`),
    resolve: (flagId: string, resolution: string, resolvedBy: string) =>
      request<AmbiguityFlag>(`/rules/ambiguity/${flagId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution, resolved_by: resolvedBy }),
      }),
  },
};
