# PolicyLens AI

**Pre-production policy compliance testing for AI agents.**

An AI agent can sound completely correct while violating company policy. PolicyLens catches those violations before the agent reaches production — by extracting structured rules from your policy documents, generating test scenarios, evaluating agent responses, and producing a launch-readiness report with dual sign-off.

**Live demo:** [policylens-ai-sand.vercel.app](https://policylens-ai-sand.vercel.app)  
**Backend API:** [policylens-ai-g207.onrender.com/docs](https://policylens-ai-g207.onrender.com/docs)

---

## The problem it solves

Teams deploying AI agents typically test for *capability* (does it answer correctly?) but not *compliance* (does it follow our specific policy?). The gap is subtle — a well-written agent will give plausible, confident answers that are still wrong under your rules.

**Real violations found during design partner testing with ShopFast:**
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
  Rule Extraction ──── Claude API extracts structured rules
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
  Dual Sign-Off ──────── QA Lead + Compliance Officer both sign
                          Release approved only when both signatures present
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg |
| Database | PostgreSQL 16 via Neon (serverless) |
| LLM | Anthropic Claude API (claude-sonnet-4-6) |
| Auth | Clerk (JWT, all routes protected) |
| Frontend | Next.js 14, TypeScript |
| Deployment | Render (backend) + Vercel (frontend) |

---

## Deployment

| Service | URL |
|---------|-----|
| Frontend | https://policylens-ai-sand.vercel.app |
| Backend API | https://policylens-ai-g207.onrender.com |
| API Docs | https://policylens-ai-g207.onrender.com/docs |

> **Note:** The Render backend is on a free tier and may take ~50 seconds to wake up after inactivity. The first request after a cold start will be slow — subsequent requests are fast.

---

## Authentication

All routes are protected by Clerk. Sign up with email or Google at the live URL. The backend verifies Clerk JWTs on every API request — unauthenticated requests return 401.

---

## Key design decisions

**Deterministic evaluation first, LLM judge second.** The evaluator runs keyword pattern matching for clear-cut cases before making an API call. The LLM judge only fires for inconclusive results or critical-tier scenarios. This keeps evaluation costs low for simple pass/fail while applying full reasoning where it matters.

**Ambiguity flags block scenario generation.** If Claude identifies a rule whose correct action depends on unstated context, it creates an `AmbiguityFlag` record that prevents scenario generation until a human resolves it in plain language. Ambiguous rules produce ambiguous tests — PolicyLens refuses to skip that step.

**Expected actions are typed, not free-form.** Scenarios specify one of nine exact expected actions: `APPROVE_FULL_REFUND`, `APPROVE_STORE_CREDIT`, `APPROVE_REPLACEMENT`, `PARTIAL_REFUND`, `DENY_RETURN`, `DENY_REFUND`, `ROUTE_TO_SELLER`, `ESCALATE_TO_CS`, `REQUEST_EVIDENCE`. The distinction between "approve refund" and "approve store credit" is exactly the class of violation PolicyLens is built to catch.

**Dual sign-off is enforced at the service layer.** A release requires exactly 2 `ReleaseSignature` records before `status` moves to `approved`. The same signer cannot sign twice. This is not a UI convention — it's a constraint enforced in the backend service.

---

## Running locally

**Without Docker**
```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # set DATABASE_URL and ANTHROPIC_API_KEY
uvicorn main:app --reload

# Frontend (new terminal)
cd frontend && npm install && npm run dev
```

Required env vars:

| Variable | Where | Description |
|----------|-------|-------------|
| `DATABASE_URL` | backend | `postgresql+asyncpg://...?ssl=require` |
| `ANTHROPIC_API_KEY` | backend | Claude API key |
| `CLERK_JWKS_URL` | backend | From Clerk dashboard → API Keys → JWKS URL |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | frontend | From Clerk dashboard |
| `CLERK_SECRET_KEY` | frontend | From Clerk dashboard |
| `NEXT_PUBLIC_API_URL` | frontend | Backend URL (e.g. `http://localhost:8000`) |

---

## API

32 endpoints across 6 routers. Full interactive docs at `/docs`.

```
GET  /health

POST /workspaces/
GET  /workspaces/
GET  /workspaces/{id}

POST /policies/upload/pdf
POST /policies/upload/text
POST /policies/upload/notion
GET  /policies/workspace/{id}
GET  /policies/{id}

POST /rules/extract/{policy_id}
GET  /rules/policy/{policy_id}
POST /rules/{id}/approve
POST /rules/{id}/edit
POST /rules/{id}/reject
GET  /rules/ambiguity/policy/{policy_id}
POST /rules/ambiguity/{id}/resolve

POST /scenarios/generate/{policy_id}
GET  /scenarios/policy/{policy_id}
POST /scenarios/policy/{id}/custom
DELETE /scenarios/policy/{id}

POST /evaluations/
POST /evaluations/{id}/upload-batch
GET  /evaluations/workspace/{id}
GET  /evaluations/{id}
GET  /evaluations/{id}/results
GET  /evaluations/{id}/findings

POST /releases/
POST /releases/{id}/sign
GET  /releases/{id}
GET  /releases/{id}/findings
POST /releases/compare
```

---

## Project structure

```
policylens-ai/
├── backend/
│   ├── main.py                     FastAPI app, Clerk JWT auth middleware
│   ├── models/                     SQLAlchemy ORM tables
│   ├── routers/                    one file per resource
│   └── services/
│       ├── ingestion.py            PDF (pdfplumber) + Notion API
│       ├── extraction.py           Claude rule extraction + ambiguity detection
│       ├── scenario_generator.py   Claude scenario generation
│       ├── evaluator.py            deterministic checker + LLM judge
│       └── report.py               release builder + dual sign-off
├── frontend/
│   ├── middleware.ts               Clerk auth — blocks all unauthenticated routes
│   ├── app/page.tsx                workspace list
│   ├── app/workspace/[id]/         workspace detail + policy upload
│   ├── app/policy/[id]/rules/      rule review + ambiguity resolution
│   └── app/evaluation/[id]/        evaluation results + release report + sign-off
└── demo/
    ├── shopfast_policy.txt         ShopFast v4.2 returns policy
    ├── simulated_agent.py          mock agent with no policy grounding
    ├── run_demo.py                 end-to-end CLI demo
    └── loom_script.md              3-minute demo video script
```

---

## Sprint history

| Sprint | Scope | Status |
|--------|-------|--------|
| 1 | Setup, DB schema, ingestion (PDF + Notion) | ✅ |
| 2 | LLM rule extraction, ambiguity flagging, rule review UI | ✅ |
| 3 | Scenario generation (normal, edge, exception, adversarial) | ✅ |
| 4 | Evaluation engine (deterministic + LLM judge, findings) | ✅ |
| 5 | Launch report, dual sign-off, version comparison | ✅ |
| 6 | End-to-end demo (ShopFast), test suite, Loom script | ✅ |
| 7 | Frontend evaluation/release UI, CORS restriction, Clerk auth | ✅ |
