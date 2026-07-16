"""
PolicyLens AI — Sprint 6 End-to-End Demo

Walks through the complete PolicyLens loop using the ShopFast v4.2 policy,
demonstrating real policy violations that a naive AI agent would make.

Usage:
  1. Start the backend:         uvicorn backend.main:app --reload --port 8000
  2. Start the agent (same app, different port):
                                uvicorn demo.simulated_agent:app --port 8001
  3. Run this script:           python demo/run_demo.py
"""

import asyncio
import sys
import os
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
AGENT_URL = "http://localhost:8001/agent/respond"
POLICY_FILE = Path(__file__).parent / "shopfast_policy.txt"

# ─── ANSI colours ─────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):    print(f"{GREEN}  [OK] {msg}{RESET}")
def fail(msg):  print(f"{RED}  [FAIL] {msg}{RESET}")
def warn(msg):  print(f"{YELLOW}  [!] {msg}{RESET}")
def info(msg):  print(f"{DIM}    {msg}{RESET}")
def header(msg):
    print(f"\n{BOLD}{CYAN}{'-' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {msg}{RESET}")
    print(f"{BOLD}{CYAN}{'-' * 60}{RESET}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def check_services(client: httpx.AsyncClient):
    """Verify both the API and simulated agent are reachable."""
    header("PRE-FLIGHT CHECK")
    try:
        r = await client.get(f"{BASE_URL}/health")
        r.raise_for_status()
        ok(f"PolicyLens API  →  {r.json()['status']} (v{r.json()['version']})")
    except Exception as e:
        fail(f"PolicyLens API unreachable at {BASE_URL}: {e}")
        sys.exit(1)

    try:
        r = await client.get("http://localhost:8001/health")
        r.raise_for_status()
        ok(f"Simulated agent →  {r.json()['status']} ({r.json()['agent']})")
    except Exception as e:
        fail(f"Simulated agent unreachable at http://localhost:8001: {e}")
        sys.exit(1)


async def poll_evaluation(client: httpx.AsyncClient, run_id: str, timeout: int = 120) -> dict:
    """Poll evaluation run until completed or failed."""
    for _ in range(timeout):
        await asyncio.sleep(1)
        r = await client.get(f"{BASE_URL}/evaluations/{run_id}")
        run = r.json()
        if run["status"] in ("completed", "failed"):
            return run
    raise TimeoutError(f"Evaluation run {run_id} did not complete within {timeout}s")


# ─── Demo steps ───────────────────────────────────────────────────────────────

async def run_demo():
    async with httpx.AsyncClient(timeout=180.0) as client:

        await check_services(client)

        # ── Step 1: Create workspace ──────────────────────────────────────────
        header("STEP 1 — Create Workspace")
        r = await client.post(f"{BASE_URL}/workspaces/", json={
            "name": "ShopFast Demo — Sprint 6",
            "description": "End-to-end demo: ShopFast v4.2 returns policy validation",
        })
        r.raise_for_status()
        workspace = r.json()
        workspace_id = workspace["id"]
        ok(f"Workspace created: {workspace['name']}")
        info(f"ID: {workspace_id}")

        # ── Step 2: Upload policy ─────────────────────────────────────────────
        header("STEP 2 — Upload ShopFast v4.2 Policy")
        policy_text = POLICY_FILE.read_text(encoding="utf-8")
        r = await client.post(f"{BASE_URL}/policies/upload/text", data={
            "workspace_id": workspace_id,
            "title": "ShopFast Return & Refund Policy v4.2",
            "raw_text": policy_text,
            "uploaded_by": "demo-runner",
        })
        r.raise_for_status()
        upload_resp = r.json()
        policy = upload_resp["policy"]
        policy_id = policy["id"]
        ok(f"Policy uploaded: {policy['title']}")
        info(f"Characters: {len(policy_text):,}  |  ID: {policy_id}")

        # ── Step 3: Extract rules ─────────────────────────────────────────────
        header("STEP 3 — Extract Policy Rules (Claude API)")
        print(f"  {DIM}Calling Claude API to extract structured rules...{RESET}")
        r = await client.post(f"{BASE_URL}/rules/extract/{policy_id}?actor=demo-runner")
        if not r.is_success:
            print(f"  Extraction error: {r.status_code} — {r.text}")
        r.raise_for_status()
        extraction = r.json()
        ok(f"Extracted {extraction['rules_extracted']} rules")
        if extraction["ambiguity_flags_created"] > 0:
            warn(f"{extraction['ambiguity_flags_created']} ambiguity flag(s) need resolution")
        info(extraction["message"])

        # ── Step 4: Print extracted rules ────────────────────────────────────
        header("STEP 4 — Review Extracted Rules")
        r = await client.get(f"{BASE_URL}/rules/policy/{policy_id}")
        r.raise_for_status()
        rules = r.json()

        print(f"\n  {'#':<5} {'STATUS':<18} {'SEVERITY':<10} {'CONDITION (truncated)'}")
        print(f"  {'─'*5} {'─'*18} {'─'*10} {'─'*42}")

        flagged_rule_ids = []
        for rule in rules:
            status_color = YELLOW if rule["has_open_ambiguity"] else (GREEN if rule["status"] == "approved" else "")
            status_label = f"{'⚑ ' if rule['has_open_ambiguity'] else ''}{rule['status']}"
            condition_short = rule["condition"][:45] + "…" if len(rule["condition"]) > 45 else rule["condition"]
            print(f"  {rule['rule_number']:<5} {status_color}{status_label:<18}{RESET} {rule['severity']:<10} {condition_short}")
            if rule["has_open_ambiguity"]:
                flagged_rule_ids.append(rule["id"])

        # ── Step 5: Resolve ambiguity flags ──────────────────────────────────
        if flagged_rule_ids:
            header("STEP 5 — Resolve Ambiguity Flags (FR-11)")
            r = await client.get(f"{BASE_URL}/rules/ambiguity/policy/{policy_id}")
            r.raise_for_status()
            flags = r.json()

            for flag in flags:
                warn(f"Ambiguity: {flag['flag_reason']}")
                resolution = (
                    "When a purchase was made using a combination of ShopFast Loyalty Points "
                    "and cash, the refund must be split proportionally: the cash portion refunded "
                    "as cash to the original payment method, and the points portion refunded as "
                    "store credit. The agent must NOT issue the full amount as cash. "
                    "Confirmed by Sarah Chen, VP Operations, June 2026."
                )
                r2 = await client.post(f"{BASE_URL}/rules/ambiguity/{flag['id']}/resolve", json={
                    "resolution": resolution,
                    "resolved_by": "sarah.chen@shopfast.com",
                })
                r2.raise_for_status()
                ok(f"Resolved: {flag['flag_reason'][:60]}…")
        else:
            header("STEP 5 — Ambiguity Flags")
            ok("No ambiguity flags — all rules are unambiguous")

        # ── Step 6: Approve all rules ─────────────────────────────────────────
        header("STEP 6 — Approve All Rules")
        r = await client.get(f"{BASE_URL}/rules/policy/{policy_id}")
        r.raise_for_status()
        rules = r.json()

        approved = 0
        for rule in rules:
            if rule["status"] in ("pending_review", "needs_resolution"):
                r2 = await client.post(f"{BASE_URL}/rules/{rule['id']}/approve", json={
                    "reviewed_by": "qa.lead@shopfast.com",
                })
                r2.raise_for_status()
                approved += 1

        ok(f"Approved {approved} rules — all rules ready for scenario generation")

        # ── Step 7: Generate scenarios ────────────────────────────────────────
        header("STEP 7 — Generate Test Scenarios (Claude API)")
        print(f"  {DIM}Calling Claude API to generate normal, edge, and adversarial scenarios...{RESET}")
        r = await client.post(f"{BASE_URL}/scenarios/generate/{policy_id}?actor=demo-runner")
        if not r.is_success:
            print(f"  Scenario gen error: {r.status_code} — {r.text}")
        r.raise_for_status()
        gen_result = r.json()
        ok(f"Generated {gen_result.get('scenarios_created', '?')} scenarios")

        # ── Step 8: Print scenario list ───────────────────────────────────────
        header("STEP 8 — Scenario Inventory")
        r = await client.get(f"{BASE_URL}/scenarios/policy/{policy_id}")
        r.raise_for_status()
        scenarios = r.json()

        by_type: dict[str, list] = {}
        for s in scenarios:
            t = s.get("scenario_type", "unknown")
            by_type.setdefault(t, []).append(s)

        for stype, items in sorted(by_type.items()):
            print(f"\n  {BOLD}{stype.upper()} ({len(items)}){RESET}")
            for s in items:
                tier_color = RED if s.get("risk_tier") == "critical" else (YELLOW if s.get("risk_tier") == "high" else DIM)
                print(f"  {tier_color}  [{s.get('risk_tier','?'):8}]{RESET}  {s['scenario_number']}  {s['title'][:55]}")

        print(f"\n  Total: {len(scenarios)} scenarios across {len(by_type)} type(s)")

        # ── Step 9: Create evaluation run ─────────────────────────────────────
        header("STEP 9 — Start Evaluation Run (Endpoint Mode)")
        print(f"  {DIM}Agent endpoint: {AGENT_URL}{RESET}")
        r = await client.post(f"{BASE_URL}/evaluations/", json={
            "policy_id": policy_id,
            "version_label": "shopfast-simulated-v1",
            "agent_type": "endpoint",
            "agent_endpoint_url": AGENT_URL,
            "model_name": "simulated-agent-v1",
            "prompt_version": "no-policy-grounding",
            "created_by": "demo-runner",
        })
        r.raise_for_status()
        run = r.json()
        run_id = run["id"]
        ok(f"Evaluation run created  (status: {run['status']})")
        info(f"Run ID: {run_id}")

        # ── Step 10: Wait for completion ──────────────────────────────────────
        header("STEP 10 — Waiting for Evaluation to Complete")
        print(f"  {DIM}PolicyLens is calling the simulated agent for each scenario...{RESET}", end="", flush=True)

        dot_count = 0
        for _ in range(120):
            await asyncio.sleep(2)
            r = await client.get(f"{BASE_URL}/evaluations/{run_id}")
            run = r.json()
            if run["status"] in ("completed", "failed"):
                break
            print(".", end="", flush=True)
            dot_count += 1
        print()

        if run["status"] == "failed":
            fail("Evaluation run failed — check backend logs")
            sys.exit(1)

        ok(f"Evaluation completed in ~{dot_count * 2}s")
        print(f"\n  {BOLD}Results:{RESET}")
        print(f"    Total scenarios:       {run['total_scenarios']}")
        print(f"    Passed:                {GREEN}{run['passed']}{RESET}")
        print(f"    Failed:                {RED}{run['failed']}{RESET}")
        print(f"    Critical violations:   {RED if run['critical_violations'] > 0 else GREEN}{run['critical_violations']}{RESET}")
        print(f"    Decision accuracy:     {GREEN if run['decision_accuracy_pct'] >= 90 else RED}{run['decision_accuracy_pct']}%{RESET}  (threshold: ≥90%)")

        # ── Step 11: Print findings ───────────────────────────────────────────
        header("STEP 11 — Policy Violations Found")
        r = await client.get(f"{BASE_URL}/evaluations/{run_id}/findings")
        r.raise_for_status()
        findings = r.json()

        if not findings:
            ok("No violations — agent is fully compliant!")
        else:
            print(f"  Found {RED}{BOLD}{len(findings)} violation(s){RESET}:\n")
            for f in findings:
                sev = f["severity"]
                sev_color = RED if sev == "critical" else YELLOW
                print(f"  {sev_color}{BOLD}[{sev.upper()}]{RESET}  {f['title']}")
                if f.get("violated_clause"):
                    info(f"Violated clause: {f['violated_clause'][:80]}")
                if f.get("likely_cause"):
                    info(f"Likely cause:    {f['likely_cause']}")
                print()

        # ── Step 12: Build launch-readiness report ────────────────────────────
        header("STEP 12 — Build Launch-Readiness Report")
        r = await client.post(f"{BASE_URL}/releases/", json={
            "evaluation_run_id": run_id,
            "created_by": "demo-runner",
        })
        if not r.is_success:
            print(f"  Release error: {r.status_code} — {r.text[:500]}")
        r.raise_for_status()
        release = r.json()
        release_id = release["id"]

        rec = release["recommendation"]
        rec_color = GREEN if rec == "ready" else (YELLOW if rec == "conditionally_ready" else RED)
        rec_label = {
            "ready": "✓ READY FOR PRODUCTION",
            "conditionally_ready": "⚠ CONDITIONALLY READY",
            "not_ready": "✗ NOT READY — DO NOT LAUNCH",
        }.get(rec, rec.upper())

        print(f"\n  {BOLD}Launch-Readiness Report{RESET}")
        print(f"  {'─' * 40}")
        print(f"  Recommendation:      {rec_color}{BOLD}{rec_label}{RESET}")
        print(f"  Reason:              {release['recommendation_reason']}")
        print(f"  Decision accuracy:   {release['decision_accuracy_pct']}%")
        print(f"  Critical violations: {release['critical_violation_rate']}%")
        print(f"  Scenario coverage:   {release['scenario_coverage_pct']}%")
        print(f"  Open findings:       {release['open_findings']}")
        print(f"  Status:              {release['status']}")

        # ── Step 13: Dual sign-off ────────────────────────────────────────────
        header("STEP 13 — Dual Sign-Off")
        print(f"  {DIM}Attempting dual sign-off even though recommendation is {rec}...{RESET}")
        print(f"  {DIM}(In production, sign-off is blocked or noted for not_ready releases){RESET}\n")

        r = await client.post(f"{BASE_URL}/releases/{release_id}/sign", json={
            "signer_name": "Alex Rivera",
            "signer_role": "qa_lead",
            "notes": "Test coverage complete. Violations documented for remediation.",
        })
        r.raise_for_status()
        sig1 = r.json()
        ok(f"Signature 1: Alex Rivera (QA Lead)  — status: {sig1['status']}")

        r = await client.post(f"{BASE_URL}/releases/{release_id}/sign", json={
            "signer_name": "Sarah Chen",
            "signer_role": "vp_operations",
            "notes": "Acknowledged. Agent must be fixed before production. Findings assigned to prompt team.",
        })
        r.raise_for_status()
        sig2 = r.json()
        ok(f"Signature 2: Sarah Chen (VP Ops)    — status: {sig2['status']}")

        final_status = sig2["status"]
        status_color = GREEN if final_status == "approved" else YELLOW
        print(f"\n  Release final status: {status_color}{BOLD}{final_status.upper()}{RESET}")

        if sig2["signatures"]:
            print(f"\n  Signatories:")
            for s in sig2["signatures"]:
                print(f"    {DIM}• {s['signer_name']} ({s['signer_role']}) — {s['signed_at'][:19]}{RESET}")

        # ── Final summary ─────────────────────────────────────────────────────
        header("DEMO COMPLETE")

        if rec == "not_ready":
            print(f"  {RED}{BOLD}PolicyLens verdict: NOT READY — Do Not Launch{RESET}")
            print(f"\n  The simulated agent violated {len(findings)} policy rule(s).")
            print(f"  Critical violations were found — these represent real financial")
            print(f"  and compliance risk if this agent were deployed to production.\n")

            critical_findings = [f for f in findings if f["severity"] == "critical"]
            major_findings    = [f for f in findings if f["severity"] == "major"]

            if critical_findings:
                print(f"  {RED}Critical (must fix before launch):{RESET}")
                for f in critical_findings:
                    print(f"    • {f['title']}")
            if major_findings:
                print(f"\n  {YELLOW}Major (fix before launch):{RESET}")
                for f in major_findings:
                    print(f"    • {f['title']}")

            print(f"\n  {YELLOW}In a real demo, you would:{RESET}")
            print(f"    1. Fix the agent's prompt to add ShopFast policy grounding")
            print(f"    2. Re-run the evaluation (use /releases/compare to see the delta)")
            print(f"    3. Watch the recommendation change from NOT READY → READY")
            print(f"    4. Complete dual sign-off on the new release")
        elif rec == "conditionally_ready":
            print(f"  {YELLOW}{BOLD}PolicyLens verdict: CONDITIONALLY READY{RESET}")
            print(f"  No critical violations, but {release['open_findings']} finding(s) remain open.")
            print(f"  Document mitigations before production launch.")
        else:
            print(f"  {GREEN}{BOLD}PolicyLens verdict: READY FOR PRODUCTION{RESET}")
            print(f"  Zero critical violations, ≥90% accuracy, all findings resolved.")
            print(f"  Dual sign-off complete — cleared for launch.")

        print(f"\n  {DIM}PolicyLens AI | Sprint 6 Demo | ShopFast v4.2{RESET}\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
