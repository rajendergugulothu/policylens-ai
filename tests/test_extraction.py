"""
Tests for services/extraction.py

Mocks the Claude API — validates that extract_rules() correctly:
- Creates PolicyRule records from Claude's response
- Creates AmbiguityFlag records for non-deterministic rules (FR-11)
- Sets correct status: pending_review vs needs_resolution
- Resolves source citations from [PAGE:N] and [BLOCK:id|URL:url] markers
- Raises ValueError for missing policy, empty text, bad JSON
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_claude_response(rules: list[dict]) -> MagicMock:
    """Build a mock Anthropic API response object."""
    content = MagicMock()
    content.text = json.dumps({"rules": rules})
    msg = MagicMock()
    msg.content = [content]
    return msg


GOOD_RULES = [
    {
        "rule_number": "R1",
        "condition": "Customer returns item within 30 days of delivery",
        "action": "Issue CASH REFUND",
        "exception": None,
        "required_evidence": None,
        "source_section": "Section 1",
        "source_page": None,
        "source_citation_url": None,
        "source_citation_text": "Customers may return within 30 days for a full cash refund.",
        "severity": "medium",
        "is_deterministic": True,
        "ambiguity_reason": None,
    },
    {
        "rule_number": "R2",
        "condition": "Item marked Final Sale at checkout",
        "action": "DENY return and DENY refund",
        "exception": "If damaged: issue STORE CREDIT ONLY",
        "required_evidence": "Photo evidence within 5 days",
        "source_section": "Section 2",
        "source_page": None,
        "source_citation_url": None,
        "source_citation_text": "Final Sale items are non-returnable.",
        "severity": "high",
        "is_deterministic": True,
        "ambiguity_reason": None,
    },
    {
        "rule_number": "R3",
        "condition": "Purchase used Loyalty Points combined with cash",
        "action": "Split refund: cash portion → cash, points portion → store credit",
        "exception": None,
        "required_evidence": None,
        "source_section": "Section 7",
        "source_page": None,
        "source_citation_url": None,
        "source_citation_text": "Must split refund proportionally.",
        "severity": "critical",
        "is_deterministic": False,
        "ambiguity_reason": "Split ratio depends on purchase proportion not stated in customer message",
    },
]


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_creates_rules(db, policy):
    """extract_rules() creates one PolicyRule per rule in Claude's response."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules
    from models.policy_rule import PolicyRule

    mock_response = _mock_claude_response(GOOD_RULES)
    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        rules = await extract_rules(db, str(policy.id))

    assert len(rules) == 3
    rule_numbers = {r.rule_number for r in rules}
    assert rule_numbers == {"R1", "R2", "R3"}


@pytest.mark.asyncio
async def test_deterministic_rules_get_pending_review(db, policy):
    """Deterministic rules (is_deterministic=True) start as pending_review."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules

    mock_response = _mock_claude_response(GOOD_RULES)
    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        rules = await extract_rules(db, str(policy.id))

    deterministic = [r for r in rules if r.rule_number in ("R1", "R2")]
    assert all(r.status == "pending_review" for r in deterministic)


@pytest.mark.asyncio
async def test_ambiguous_rule_gets_needs_resolution(db, policy):
    """Non-deterministic rules (is_deterministic=False) get status=needs_resolution (FR-11)."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules

    mock_response = _mock_claude_response(GOOD_RULES)
    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        rules = await extract_rules(db, str(policy.id))

    ambiguous = next(r for r in rules if r.rule_number == "R3")
    assert ambiguous.status == "needs_resolution"


@pytest.mark.asyncio
async def test_ambiguity_flag_created_for_non_deterministic(db, policy):
    """An AmbiguityFlag record is created for each non-deterministic rule."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules
    from models.policy_rule import AmbiguityFlag

    mock_response = _mock_claude_response(GOOD_RULES)
    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        rules = await extract_rules(db, str(policy.id))

    ambiguous_rule = next(r for r in rules if r.rule_number == "R3")
    flag_result = await db.execute(
        select(AmbiguityFlag).where(AmbiguityFlag.rule_id == ambiguous_rule.id)
    )
    flags = flag_result.scalars().all()
    assert len(flags) == 1
    assert flags[0].status == "open"
    assert "proportion" in flags[0].flag_reason.lower()


@pytest.mark.asyncio
async def test_no_flag_for_deterministic_rules(db, policy):
    """No AmbiguityFlag is created for deterministic rules."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules
    from models.policy_rule import AmbiguityFlag

    mock_response = _mock_claude_response(GOOD_RULES)
    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        rules = await extract_rules(db, str(policy.id))

    deterministic_ids = [r.id for r in rules if r.rule_number in ("R1", "R2")]
    flag_result = await db.execute(
        select(AmbiguityFlag).where(AmbiguityFlag.rule_id.in_(deterministic_ids))
    )
    assert len(flag_result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_raises_for_missing_policy(db):
    """ValueError raised when policy_id does not exist."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules

    with pytest.raises(ValueError, match="not found"):
        await extract_rules(db, "00000000-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_raises_for_empty_policy_text(db, workspace):
    """ValueError raised when policy has no raw_text."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules
    from models.policy import Policy

    empty_policy = Policy(
        workspace_id=workspace.id,
        title="Empty Policy",
        raw_text="",
        source_format="plain_text",
        version_label="v1.0",
        is_active=True,
    )
    db.add(empty_policy)
    await db.flush()

    with pytest.raises(ValueError, match="no extracted text"):
        await extract_rules(db, str(empty_policy.id))


@pytest.mark.asyncio
async def test_raises_for_invalid_json_response(db, policy):
    """ValueError raised when Claude returns non-JSON."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules

    bad_content = MagicMock()
    bad_content.text = "Sorry, I cannot help with that."
    bad_msg = MagicMock()
    bad_msg.content = [bad_content]

    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=bad_msg)
        with pytest.raises(ValueError, match="invalid JSON"):
            await extract_rules(db, str(policy.id))


@pytest.mark.asyncio
async def test_page_marker_resolves_source_page(db, workspace):
    """[PAGE:N] markers in raw text are used to set source_page on the rule."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules
    from models.policy import Policy

    pdf_policy = Policy(
        workspace_id=workspace.id,
        title="PDF Policy",
        raw_text="[PAGE:3]\nSection 1 — Standard Returns\nCustomers may return within 30 days.",
        source_format="pdf",
        version_label="v1.0",
        is_active=True,
    )
    db.add(pdf_policy)
    await db.flush()

    pdf_rule = [{
        **GOOD_RULES[0],
        "source_section": "Section 1",
        "source_page": None,
    }]
    mock_response = _mock_claude_response(pdf_rule)
    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        rules = await extract_rules(db, str(pdf_policy.id))

    assert rules[0].source_page == 3


@pytest.mark.asyncio
async def test_notion_block_marker_resolves_citation_url(db, workspace):
    """[BLOCK:id|URL:url] markers are used to set source_citation_url on the rule."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.extraction import extract_rules
    from models.policy import Policy

    notion_url = "https://notion.so/page#block-abc123"
    notion_policy = Policy(
        workspace_id=workspace.id,
        title="Notion Policy",
        raw_text=f"[BLOCK:abc123|URL:{notion_url}]\nSection 1 — Standard Returns\nCustomers may return within 30 days.",
        source_format="notion_url",
        version_label="v1.0",
        is_active=True,
    )
    db.add(notion_policy)
    await db.flush()

    notion_rule = [{
        **GOOD_RULES[0],
        "source_section": "Section 1",
        "source_citation_url": None,
    }]
    mock_response = _mock_claude_response(notion_rule)
    with patch("services.extraction.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        rules = await extract_rules(db, str(notion_policy.id))

    assert rules[0].source_citation_url == notion_url
