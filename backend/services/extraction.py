"""
Rule extraction service.

Takes raw policy text (with [PAGE:N] and [BLOCK:id|URL:url] markers from ingestion)
and produces structured PolicyRule records via the Claude API.

Key decisions:
- Single API call extracts all rules + flags ambiguity simultaneously
- Source citation is built from markers in the raw text, not a separate index
- is_deterministic=false triggers an AmbiguityFlag (FR-11) and blocks scenario generation
- Rules start as status='pending_review' — humans approve before any testing begins
"""

import json
import re
import os
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.policy import Policy
from models.policy_rule import PolicyRule, AmbiguityFlag
from models.audit import AuditLog

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

EXTRACTION_SYSTEM = """You are PolicyLens AI, a policy analysis system for enterprise AI governance.
Your job is to extract structured, testable rules from policy documents.
You return ONLY valid JSON. No markdown. No backticks. No explanation. No preamble."""

EXTRACTION_PROMPT = """Extract all rules from this policy document. The text contains source markers:
- [PAGE:N] marks the PDF page number of the text that follows
- [BLOCK:id|URL:url] marks the Notion block ID and direct anchor URL

For each rule, include the condition, action, and any exceptions or evidence requirements.
Be specific about action type — do not say "issue refund" if the policy specifies "issue STORE CREDIT" or "issue CASH REFUND". The distinction is critical.

Mark is_deterministic as false if:
1. Two reasonable people reading the clause would take different agent actions
2. The action depends on judgment or context not stated in the policy
3. The clause references external standards not present in this document

Return exactly this JSON structure, nothing else:
{{
  "rules": [
    {{
      "rule_number": "R1",
      "condition": "specific condition when this rule applies",
      "action": "exactly what the agent must do (include refund type: cash / store credit / replacement)",
      "exception": "override condition that changes the action, or null",
      "required_evidence": "what proof the customer must provide, or null",
      "source_section": "section name or number from the document",
      "source_page": null_or_integer,
      "source_citation_url": "block anchor URL from [BLOCK:id|URL:...] marker, or null",
      "source_citation_text": "verbatim policy text this rule is based on (max 200 chars)",
      "severity": "critical or high or medium or low",
      "is_deterministic": true,
      "ambiguity_reason": null
    }}
  ]
}}

Severity guide:
  critical — violation causes financial loss or regulatory breach (e.g. wrong refund type, wrong routing)
  high     — violation produces wrong outcome for customer (e.g. wrong date window)
  medium   — violation causes incorrect escalation or explanation
  low      — minor procedure or wording issue

Policy document:
{policy_text}"""


def _find_source_citation_url(raw_text: str, source_section: str) -> str | None:
    """
    Walk the raw text to find the BLOCK marker nearest to the cited section.
    Used to build Notion deep links for source citations.
    """
    if not source_section:
        return None
    pattern = r"\[BLOCK:[^|]+\|URL:([^\]]+)\]"
    matches = list(re.finditer(pattern, raw_text))
    if not matches:
        return None
    # Find the block marker closest to (and before) the section text
    section_pos = raw_text.lower().find(source_section.lower())
    if section_pos == -1:
        return matches[0].group(1) if matches else None
    preceding = [m for m in matches if m.start() <= section_pos]
    if preceding:
        return preceding[-1].group(1)
    return matches[0].group(1)


def _find_source_page(raw_text: str, source_section: str) -> int | None:
    """
    Find the PDF page number nearest to the cited section.
    Page markers look like [PAGE:3].
    """
    if not source_section:
        return None
    section_pos = raw_text.lower().find(source_section.lower())
    if section_pos == -1:
        return None
    # Find all PAGE markers
    pattern = r"\[PAGE:(\d+)\]"
    matches = list(re.finditer(pattern, raw_text))
    preceding = [m for m in matches if m.start() <= section_pos]
    if preceding:
        return int(preceding[-1].group(1))
    return None


async def extract_rules(
    db: AsyncSession,
    policy_id: str,
    actor: str = "system",
) -> list[PolicyRule]:
    """
    Extract rules from a policy using the Claude API.
    Creates PolicyRule and AmbiguityFlag records.
    Rules start as status='pending_review'.
    Ambiguous rules (is_deterministic=false) get status='needs_resolution'.
    """
    # Fetch the policy
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise ValueError(f"Policy {policy_id} not found.")
    if not policy.raw_text:
        raise ValueError("Policy has no extracted text. Run ingestion first.")

    # Call Claude
    prompt = EXTRACTION_PROMPT.format(policy_text=policy.raw_text)
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_response = message.content[0].text.strip()

    # Strip any accidental markdown fences
    raw_response = re.sub(r"^```json\s*", "", raw_response)
    raw_response = re.sub(r"\s*```$", "", raw_response)

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw response:\n{raw_response[:500]}")

    rules_data = data.get("rules", [])
    if not rules_data:
        raise ValueError("Claude returned no rules. Check that the policy text is not empty.")

    created_rules: list[PolicyRule] = []

    for i, rule_data in enumerate(rules_data, start=1):
        is_deterministic = rule_data.get("is_deterministic", True)
        status = "pending_review" if is_deterministic else "needs_resolution"

        # Resolve source citation — prefer what Claude found, fall back to marker search
        source_page = rule_data.get("source_page")
        source_citation_url = rule_data.get("source_citation_url")

        if not source_citation_url and policy.source_format == "notion_url":
            source_citation_url = _find_source_citation_url(
                policy.raw_text, rule_data.get("source_section", "")
            )
        if not source_page and policy.source_format == "pdf":
            source_page = _find_source_page(
                policy.raw_text, rule_data.get("source_section", "")
            )

        rule = PolicyRule(
            policy_id=policy.id,
            rule_number=rule_data.get("rule_number", f"R{i}"),
            condition=rule_data.get("condition", ""),
            action=rule_data.get("action", ""),
            exception=rule_data.get("exception"),
            required_evidence=rule_data.get("required_evidence"),
            source_section=rule_data.get("source_section"),
            source_page=source_page,
            source_citation_url=source_citation_url,
            severity=rule_data.get("severity", "high"),
            status=status,
            notes=rule_data.get("source_citation_text"),  # store citation text in notes
        )
        db.add(rule)
        await db.flush()

        # Create ambiguity flag if not deterministic (FR-11)
        if not is_deterministic and rule_data.get("ambiguity_reason"):
            flag = AmbiguityFlag(
                rule_id=rule.id,
                flagged_clause=rule_data.get("source_citation_text", rule.condition),
                flag_reason=rule_data["ambiguity_reason"],
                status="open",
            )
            db.add(flag)

        created_rules.append(rule)

    # Audit log entry
    db.add(AuditLog(
        workspace_id=policy.workspace_id,
        entity_type="policy",
        entity_id=policy.id,
        action="rules_extracted",
        actor=actor,
        new_value={
            "rule_count": len(created_rules),
            "model": "claude-sonnet-4-6",
        },
    ))

    return created_rules
