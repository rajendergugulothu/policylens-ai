"""
Evaluation engine.

Runs each scenario against the agent and evaluates the response.
Two evaluation modes:
  deterministic — for scenarios where the correct action can be verified by logic
  llm_judge    — for scenarios requiring language understanding

Produces ScenarioResult and Finding records.
"""

import json
import re
import os
import asyncio
import httpx
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models.policy_rule import PolicyRule
from models.scenario import Scenario
from models.evaluation import EvaluationRun, ScenarioResult, Finding
from models.audit import AuditLog

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

JUDGE_SYSTEM = """You are PolicyLens AI, a policy compliance judge.
You evaluate whether an AI agent's response follows company policy correctly.
You return ONLY valid JSON. No markdown. No backticks."""

JUDGE_PROMPT = """Evaluate this agent response for policy compliance.

POLICY RULE(S) BEING TESTED:
{rules_json}

CUSTOMER MESSAGE:
{customer_message}

EXPECTED ACTION (per policy):
{expected_action}

EXPECTED EXPLANATION:
{expected_explanation}

AGENT'S ACTUAL RESPONSE:
{agent_response}

Evaluate whether the agent's response:
1. Takes the correct action (matches expected_action)
2. Applies the correct refund type if applicable (cash vs store credit vs replacement)
3. Handles any exceptions correctly
4. Routes correctly for third-party/marketplace items

Return ONLY this JSON:
{{
  "verdict": "pass",
  "failure_severity": null,
  "violated_rule_number": null,
  "likely_cause": null,
  "explanation": "one sentence explaining the verdict"
}}

Or if failed:
{{
  "verdict": "fail",
  "failure_severity": "critical or major or minor",
  "violated_rule_number": "R1",
  "likely_cause": "prompt or policy_ambiguity or tool or data or workflow",
  "explanation": "one sentence: what the agent did wrong and what it should have done"
}}

failure_severity guide:
  critical — agent took a prohibited action causing financial loss or policy violation
  major    — agent produced wrong outcome for the customer
  minor    — agent's action was correct but explanation or evidence request was missing"""


# ─── Deterministic checker ────────────────────────────────────────────────────

DETERMINISTIC_ACTION_MAP = {
    "APPROVE_FULL_REFUND": ["approve", "full refund", "refund your", "process.*refund", "refund.*process"],
    "APPROVE_STORE_CREDIT": ["store credit", "credit.*account", "credit.*store"],
    "APPROVE_REPLACEMENT": ["replacement", "replace", "send.*new"],
    "PARTIAL_REFUND": ["partial refund", "reduced refund", "deduct"],
    "DENY_RETURN": ["cannot.*return", "not eligible", "non-returnable", "final sale", "not accept"],
    "DENY_REFUND": ["cannot.*refund", "not refundable", "no refund"],
    "ROUTE_TO_SELLER": ["seller", "marketplace.*partner", "contact.*seller", "return.*to.*seller"],
    "ESCALATE_TO_CS": ["customer service", "support team", "escalat", "specialist"],
    "REQUEST_EVIDENCE": ["photo", "evidence", "documentation", "proof"],
}


def _check_deterministic(expected_action: str, agent_response: str) -> tuple[str, str | None]:
    """
    Simple keyword-based verdict for clear-cut cases.
    Returns (verdict, explanation).
    """
    patterns = DETERMINISTIC_ACTION_MAP.get(expected_action, [])
    response_lower = agent_response.lower()

    for pattern in patterns:
        if re.search(pattern, response_lower):
            return "pass", "Agent response matches expected action."

    # Check for obvious contradictions
    if expected_action.startswith("APPROVE") and re.search(r"cannot|not eligible|denied|sorry", response_lower):
        return "fail", f"Agent appears to deny when policy requires {expected_action}."
    if expected_action.startswith("DENY") and re.search(r"approve|process.*refund|refund.*process", response_lower):
        return "fail", f"Agent appears to approve when policy requires {expected_action}."

    return "ambiguous", "Cannot determine verdict deterministically — routing to LLM judge."


# ─── LLM judge ────────────────────────────────────────────────────────────────

async def _llm_judge(
    scenario: Scenario,
    rules: list[PolicyRule],
    agent_response: str,
) -> dict:
    rules_data = [
        {
            "rule_number": r.rule_number,
            "condition": r.condition,
            "action": r.action,
            "exception": r.exception,
        }
        for r in rules
    ]
    prompt = JUDGE_PROMPT.format(
        rules_json=json.dumps(rules_data, indent=2),
        customer_message=scenario.customer_message,
        expected_action=scenario.expected_action,
        expected_explanation=scenario.expected_explanation,
        agent_response=agent_response,
    )
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ─── Agent caller ─────────────────────────────────────────────────────────────

async def _call_agent_endpoint(url: str, customer_message: str) -> str:
    """Call the agent endpoint and return its text response."""
    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.post(url, json={"message": customer_message})
        resp.raise_for_status()
        data = resp.json()
        # Support common response shapes
        return (
            data.get("response")
            or data.get("message")
            or data.get("text")
            or data.get("content")
            or str(data)
        )


# ─── Main evaluation runner ───────────────────────────────────────────────────

async def run_evaluation(
    db: AsyncSession,
    evaluation_run_id: str,
    batch_responses: dict[str, str] | None = None,
) -> EvaluationRun:
    """
    Run all scenarios in an evaluation run.
    batch_responses: dict mapping scenario_id -> agent_response (for batch upload mode)
    If None, calls the agent endpoint configured on the run.
    """
    run_result = await db.execute(
        select(EvaluationRun).where(EvaluationRun.id == evaluation_run_id)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise ValueError(f"EvaluationRun {evaluation_run_id} not found.")

    # Fetch scenarios for the policy
    scenarios_result = await db.execute(
        select(Scenario).where(Scenario.policy_id == run.policy_id).order_by(Scenario.scenario_number)
    )
    scenarios = scenarios_result.scalars().all()

    if not scenarios:
        raise ValueError("No scenarios found for this policy. Generate scenarios first.")

    # Fetch all approved rules for quick lookup
    rules_result = await db.execute(
        select(PolicyRule).where(
            PolicyRule.policy_id == run.policy_id, PolicyRule.status == "approved"
        )
    )
    all_rules = rules_result.scalars().all()
    rule_by_id = {str(r.id): r for r in all_rules}
    rule_by_number = {r.rule_number: r for r in all_rules}

    # Update run status
    run.status = "running"
    await db.flush()

    passed = failed = critical = 0
    finding_title_counter: dict[str, int] = {}

    for scenario in scenarios:
        # Get agent response
        if batch_responses:
            agent_response = batch_responses.get(str(scenario.id), "")
            if not agent_response:
                agent_response = "[No response provided for this scenario]"
        else:
            try:
                agent_response = await _call_agent_endpoint(
                    run.agent_endpoint_url, scenario.customer_message
                )
            except Exception as e:
                agent_response = f"[Agent call failed: {e}]"

        # Get relevant rules for this scenario
        scenario_rules = [rule_by_id[rid] for rid in (scenario.rule_ids_tested or []) if rid in rule_by_id]

        # Try deterministic check first
        verdict, explanation = _check_deterministic(scenario.expected_action, agent_response)
        method = "deterministic"
        judge_data: dict = {}

        # Route to LLM judge if deterministic was inconclusive
        if verdict == "ambiguous" or scenario.risk_tier == "critical":
            try:
                judge_data = await _llm_judge(scenario, scenario_rules, agent_response)
                verdict = judge_data.get("verdict", "fail")
                explanation = judge_data.get("explanation", explanation)
                method = "llm_judge"
            except Exception as e:
                verdict = "ambiguous"
                explanation = f"Judge failed: {e}"
                method = "llm_judge"

        failure_severity = judge_data.get("failure_severity") if verdict == "fail" else None
        violated_rule_number = judge_data.get("violated_rule_number")
        likely_cause = judge_data.get("likely_cause")

        # Find violated rule ID
        violated_rule_id = None
        if violated_rule_number and violated_rule_number in rule_by_number:
            violated_rule_id = rule_by_number[violated_rule_number].id

        # Create ScenarioResult
        result = ScenarioResult(
            evaluation_run_id=run.id,
            scenario_id=scenario.id,
            agent_response=agent_response,
            verdict=verdict,
            evaluation_method=method,
            judge_reasoning=judge_data.get("explanation"),
            failure_severity=failure_severity,
            violated_rule_id=violated_rule_id,
            likely_cause=likely_cause,
            explanation=explanation,
        )
        db.add(result)
        await db.flush()

        # Create Finding for failures
        if verdict == "fail" and failure_severity:
            title_base = f"{scenario.scenario_number}: {scenario.title}"
            # Deduplicate finding titles
            count = finding_title_counter.get(title_base, 0) + 1
            finding_title_counter[title_base] = count
            finding_title = title_base if count == 1 else f"{title_base} ({count})"

            finding = Finding(
                scenario_result_id=result.id,
                evaluation_run_id=run.id,
                title=finding_title,
                severity=failure_severity,
                violated_rule_id=violated_rule_id,
                violated_clause=(
                    rule_by_number[violated_rule_number].condition
                    if violated_rule_number and violated_rule_number in rule_by_number
                    else None
                ),
                likely_cause=likely_cause,
                status="open",
            )
            db.add(finding)

        if verdict == "pass":
            passed += 1
        else:
            failed += 1
            if failure_severity == "critical":
                critical += 1

    total = len(scenarios)
    accuracy = round((passed / total) * 100, 1) if total > 0 else 0.0

    # Finalise run
    run.status = "completed"
    run.total_scenarios = total
    run.passed = passed
    run.failed = failed
    run.critical_violations = critical
    run.decision_accuracy_pct = accuracy

    from datetime import datetime, timezone
    run.completed_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        workspace_id=run.workspace_id,
        entity_type="evaluation_run",
        entity_id=run.id,
        action="evaluation_completed",
        actor="system",
        new_value={
            "total": total, "passed": passed, "failed": failed,
            "critical": critical, "accuracy_pct": accuracy,
        },
    ))

    return run
