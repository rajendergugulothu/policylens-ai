"""
Scenario generation service.

Takes approved PolicyRule records and produces Scenario records via Claude API.
Generates normal, edge, exception, and adversarial scenarios.
Each scenario gets an expected_action and expected_explanation from the expected outcome engine.
"""

import json
import re
import os
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.policy import Policy
from models.policy_rule import PolicyRule, AmbiguityFlag
from models.scenario import Scenario
from models.audit import AuditLog

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

SCENARIO_SYSTEM = """You are PolicyLens AI, a policy compliance testing system.
You generate realistic test scenarios for AI refund agents.
You return ONLY valid JSON. No markdown. No backticks. No explanation."""

SCENARIO_PROMPT = """Generate test scenarios for an AI refund agent based on these approved policy rules.

APPROVED RULES:
{rules_json}

Generate scenarios in these categories:
- normal: straightforward case where the main rule applies correctly
- edge: boundary condition that tests the limits of the rule (date cutoffs, price thresholds, category boundaries)
- exception: a case where an exception clause overrides the main rule (only if the rule has an exception)
- adversarial: a single customer message that involves 2 or more rules simultaneously, designed to expose conflicts or gaps in agent logic

Coverage targets (keep total under 25 scenarios):
- 1 normal scenario per rule (pick the most important rules if there are many)
- 1 edge scenario per high-severity rule only
- 1 exception scenario for rules that have exception fields
- 2–3 adversarial scenarios combining critical-severity rules
Keep customer_message concise (2–3 sentences max).

The customer_message should sound like a real customer submitting a support ticket — natural, first-person, specific.

For expected_action, use one of these exact values:
APPROVE_FULL_REFUND | APPROVE_STORE_CREDIT | APPROVE_REPLACEMENT | PARTIAL_REFUND |
DENY_RETURN | DENY_REFUND | ROUTE_TO_SELLER | ESCALATE_TO_CS | REQUEST_EVIDENCE

Return ONLY this JSON:
{{
  "scenarios": [
    {{
      "title": "short descriptive title",
      "rule_numbers_tested": ["R1", "R2"],
      "scenario_type": "normal",
      "customer_message": "natural customer message as they would write it",
      "expected_action": "APPROVE_FULL_REFUND",
      "expected_explanation": "policy requires this because [cite specific rule condition and action]",
      "risk_tier": "critical"
    }}
  ]
}}

risk_tier guide:
  critical — wrong action causes financial loss or regulatory violation
  standard — wrong action produces an incorrect customer outcome
  low       — wrong action is a minor process deviation

Approved rules for reference:
{rules_json}"""


async def generate_scenarios(
    db: AsyncSession,
    policy_id: str,
    actor: str = "system",
) -> list[Scenario]:
    """
    Generate test scenarios from approved rules for a policy.
    Requires: all rules must be approved and no open ambiguity flags.
    """
    # Fetch policy
    pol_result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = pol_result.scalar_one_or_none()
    if not policy:
        raise ValueError(f"Policy {policy_id} not found.")

    # Fetch approved rules only
    rules_result = await db.execute(
        select(PolicyRule)
        .where(PolicyRule.policy_id == policy_id, PolicyRule.status == "approved")
        .order_by(PolicyRule.rule_number)
    )
    rules = rules_result.scalars().all()

    if not rules:
        raise ValueError("No approved rules found. Approve at least one rule before generating scenarios.")

    # Block if open ambiguity flags exist
    open_flags = await db.scalar(
        select(AmbiguityFlag)
        .join(PolicyRule, AmbiguityFlag.rule_id == PolicyRule.id)
        .where(
            PolicyRule.policy_id == policy_id,
            AmbiguityFlag.status == "open"
        )
    )
    if open_flags:
        raise ValueError("Open ambiguity flags exist. Resolve all flags before generating scenarios.")

    # Check for existing scenarios
    existing = await db.scalar(
        select(Scenario).where(Scenario.policy_id == policy_id)
    )
    if existing:
        raise ValueError("Scenarios already exist for this policy. Delete them before regenerating.")

    # Build rules JSON for the prompt
    rules_data = [
        {
            "rule_number": r.rule_number,
            "condition": r.condition,
            "action": r.action,
            "exception": r.exception,
            "required_evidence": r.required_evidence,
            "severity": r.severity,
            "source_section": r.source_section,
        }
        for r in rules
    ]
    rules_json = json.dumps(rules_data, indent=2)

    # Call Claude
    prompt = SCENARIO_PROMPT.format(rules_json=rules_json)
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=SCENARIO_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw:\n{raw[:400]}")

    scenarios_data = data.get("scenarios", [])
    if not scenarios_data:
        raise ValueError("No scenarios generated. Check that approved rules have enough detail.")

    # Build a lookup from rule_number → rule.id
    rule_map = {r.rule_number: r.id for r in rules}

    created: list[Scenario] = []
    for i, s in enumerate(scenarios_data, start=1):
        # Resolve rule IDs from rule numbers
        rule_ids = [
            str(rule_map[rn]) for rn in s.get("rule_numbers_tested", []) if rn in rule_map
        ]

        scenario = Scenario(
            policy_id=policy.id,
            scenario_number=f"S{i}",
            title=s.get("title", f"Scenario {i}"),
            customer_message=s.get("customer_message", ""),
            scenario_type=s.get("scenario_type", "normal"),
            rule_ids_tested=rule_ids,
            expected_action=s.get("expected_action", "DENY_RETURN"),
            expected_explanation=s.get("expected_explanation", ""),
            risk_tier=s.get("risk_tier", "standard"),
            is_custom=False,
        )
        db.add(scenario)
        created.append(scenario)

    await db.flush()

    # Audit
    db.add(AuditLog(
        workspace_id=policy.workspace_id,
        entity_type="policy",
        entity_id=policy.id,
        action="scenarios_generated",
        actor=actor,
        new_value={
            "scenario_count": len(created),
            "model": "claude-sonnet-4-6",
            "rules_used": len(rules),
        },
    ))

    return created
