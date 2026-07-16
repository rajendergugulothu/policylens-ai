# PolicyLens AI — Sprint 6 Demo

End-to-end walkthrough of the complete PolicyLens loop using the **ShopFast v4.2**
returns policy — the same policy used in the design partner session with Sarah Chen,
VP Operations. The demo catches real policy violations a naive AI agent would make.

## What you'll see

| Step | What happens |
|------|-------------|
| Policy upload | ShopFast v4.2 7-section returns policy ingested |
| Rule extraction | Claude extracts 7 structured rules; 1 ambiguity flag triggered |
| Human review | Ambiguity resolved, all rules approved |
| Scenario generation | Claude generates ~18 test scenarios (normal, edge, adversarial) |
| Evaluation | Simulated agent called for each scenario; LLM judge evaluates responses |
| Findings | 4–5 violations surfaced, including 2 critical |
| Report | Launch recommendation: **NOT READY** |
| Sign-off | Dual sign-off recorded (QA Lead + VP Ops) |

## The four violations PolicyLens catches

These are the exact violations found during the manual concierge test:

1. **Critical** — Final Sale damaged item → agent issues cash refund (policy: store credit only)
2. **Critical** — Loyalty points purchase → agent issues full cash (policy: split cash + store credit)
3. **Major** — Apple holiday return → agent uses Jan 31 deadline (policy: Jan 15)
4. **Major** — Marketplace item → agent processes direct refund (policy: route to seller first)

A well-grounded agent would get all of these right. The simulated agent uses
general-purpose reasoning with no ShopFast policy grounding — exactly what
gets deployed before teams have a tool like PolicyLens.

## Prerequisites

- Python 3.12+
- PostgreSQL 16 running (or Docker)
- `ANTHROPIC_API_KEY` set in `backend/.env`
- Backend dependencies installed: `pip install -r backend/requirements.txt`
- `httpx` installed in your demo environment: `pip install httpx`

## Running the demo (< 5 minutes)

**Terminal 1 — Start the database (if using Docker)**
```bash
docker-compose up -d db
```

**Terminal 2 — Start the PolicyLens backend**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 3 — Start the simulated agent**
```bash
# From the project root
uvicorn demo.simulated_agent:app --port 8001
```

**Terminal 4 — Run the demo**
```bash
# From the project root
python demo/run_demo.py
```

The demo runs fully automated — no input required. Watch the terminal output
to see PolicyLens work through every step of the compliance testing loop.

## Expected runtime

| Stage | Time |
|-------|------|
| Rule extraction (Claude API) | ~5–10s |
| Scenario generation (Claude API) | ~10–15s |
| Evaluation (18 scenarios × agent call + judge) | ~30–60s |
| Everything else | < 2s |
| **Total** | **~1–2 minutes** |

## Expected output

See [`expected_output.txt`](expected_output.txt) for a sample of what the terminal
should look like on a successful run.

## Troubleshooting

**`PolicyLens API unreachable`** — make sure the backend is running on port 8000.

**`Simulated agent unreachable`** — make sure `demo.simulated_agent:app` is running
on port 8001. Note: run from the project root so Python can find the `demo` module.

**`409 Rules already extracted`** — the demo creates a fresh workspace each run,
but if you reuse a policy ID, extraction will be blocked. Just re-run the demo
(it creates a new workspace each time).

**Claude API errors** — check `ANTHROPIC_API_KEY` is set and valid in `backend/.env`.
