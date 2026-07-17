# PolicyLens AI

**Pre-production policy compliance testing for AI agents.**

An AI agent can sound completely correct while violating company policy. PolicyLens catches those violations before the agent reaches production — by extracting structured rules from your policy documents, generating test scenarios, evaluating agent responses, and producing a launch-readiness report with dual sign-off.

---

## The problem it solves

Teams deploying AI agents typically test for *capability* (does it answer correctly?) but not *compliance* (does it follow our specific policy?). The gap is subtle — a well-written agent will give plausible, confident answers that are still wrong under your rules.

**Real violations found during testing with ShopFast:**
- Agent approved a **cash refund** on a Final Sale damaged item — policy requires store credit only
- Agent applied the **January 31** holiday deadline to Apple products — policy says January 15
- Agent processed a **direct refund** on a marketplace item — policy requires routing to the seller first
- Agent issued the **full refund as cash** on a loyalty points purchase — policy requires a proportional split

None of these would be caught by standard QA. All of them have real financial or legal consequences at scale.

---

## How it works

```
Policy document (PDF / text / Notion)
        │
        ▼
  Rule Extraction ──── Claude extracts structured IF/THEN rules
        │                with condition, action, exception, severity
        │
        ▼
  Human Review ──────── Policy team approves rules in the UI
        │                Ambiguity flags block testing until resolved
        │
        ▼
  Scenario Generation ── Claude generates normal, edge, and adversarial
        │                  test scenarios per rule
        │
        ▼
  Evaluation ─────────── Agent is called for each scenario
        │                  Deterministic checker → LLM judge for edge cases
        │
        ▼
  Launch Report ─────── Ready / Conditionally Ready / Not Ready
        │                  Critical violations block launch recommendation
        │
        ▼
  Dual Sign-Off ──────── Two stakeholders sign before release is approved
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async |
| Database | PostgreSQL 16 |
| LLM | Anthropic Claude API |
| Auth | Clerk (JWT, all routes protected) |
| Frontend | Next.js 14, TypeScript |

---

## Key design decisions

**Deterministic evaluation first, LLM judge second.** The evaluator runs keyword pattern matching for clear-cut cases before making an API call. The LLM judge only fires for inconclusive results or critical-tier scenarios.

**Ambiguity flags block scenario generation.** If Claude identifies a rule whose correct action depends on unstated context, it creates an ambiguity flag that prevents scenario generation until a human resolves it in plain language.

**Expected actions are typed, not free-form.** Scenarios specify one of nine exact expected actions — `APPROVE_FULL_REFUND`, `APPROVE_STORE_CREDIT`, `DENY_RETURN`, `ROUTE_TO_SELLER`, etc. The distinction between these is exactly the class of violation PolicyLens is built to catch.

**Dual sign-off is enforced at the service layer.** A release requires exactly 2 signatures before status moves to approved. The same signer cannot sign twice. This is not a UI convention — it's a backend constraint.
