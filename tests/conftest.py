"""
Shared fixtures for PolicyLens test suite.

Uses an in-memory SQLite database so tests run without PostgreSQL.
Claude API calls are mocked — tests validate logic, not LLM outputs.
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db():
    """Provide a fresh in-memory database for each test."""
    # Import models here so SQLAlchemy metadata is populated
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

    from database import Base

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def workspace(db):
    """A saved Workspace record."""
    from models.workspace import Workspace
    ws = Workspace(name="Test Workspace", description="pytest fixture")
    db.add(ws)
    await db.flush()
    return ws


@pytest_asyncio.fixture
async def policy(db, workspace):
    """A saved Policy record with raw text."""
    from models.policy import Policy
    pol = Policy(
        workspace_id=workspace.id,
        title="Test Policy",
        raw_text=_SHOPFAST_MINI_POLICY,
        source_format="plain_text",
        version_label="v1.0",
        is_active=True,
    )
    db.add(pol)
    await db.flush()
    return pol


@pytest_asyncio.fixture
async def approved_rules(db, policy):
    """A set of approved PolicyRule records."""
    from models.policy_rule import PolicyRule
    from datetime import datetime, timezone
    rules_data = [
        {
            "rule_number": "R1",
            "condition": "Customer returns item within 30 days of delivery",
            "action": "Issue CASH REFUND to original payment method",
            "exception": None,
            "severity": "medium",
            "status": "approved",
        },
        {
            "rule_number": "R2",
            "condition": "Item marked Final Sale at checkout",
            "action": "DENY return and DENY refund",
            "exception": "If item arrives damaged, issue STORE CREDIT ONLY",
            "severity": "high",
            "status": "approved",
        },
        {
            "rule_number": "R3",
            "condition": "Item sold by ShopFast Marketplace partner",
            "action": "ROUTE return request to seller — do NOT process direct refund",
            "exception": "If seller does not respond within 48 hours, process ShopFast Guarantee refund",
            "severity": "critical",
            "status": "approved",
        },
    ]
    rules = []
    for rd in rules_data:
        r = PolicyRule(
            policy_id=policy.id,
            reviewed_by="qa@test.com",
            reviewed_at=datetime.now(timezone.utc),
            **rd,
        )
        db.add(r)
        rules.append(r)
    await db.flush()
    return rules


@pytest_asyncio.fixture
async def scenarios(db, policy, approved_rules):
    """A set of Scenario records for evaluation tests."""
    from models.scenario import Scenario
    rule_map = {r.rule_number: str(r.id) for r in approved_rules}
    scenarios_data = [
        {
            "scenario_number": "S1",
            "title": "Standard return within window",
            "customer_message": "I want to return my order, it's only been 15 days.",
            "scenario_type": "normal",
            "expected_action": "APPROVE_FULL_REFUND",
            "expected_explanation": "Within 30-day window, standard item",
            "risk_tier": "standard",
            "rule_ids_tested": [rule_map["R1"]],
        },
        {
            "scenario_number": "S2",
            "title": "Final Sale damaged — should be store credit",
            "customer_message": "My Final Sale item arrived completely cracked. I want a cash refund.",
            "scenario_type": "adversarial",
            "expected_action": "APPROVE_STORE_CREDIT",
            "expected_explanation": "Final Sale damaged: store credit only, not cash",
            "risk_tier": "critical",
            "rule_ids_tested": [rule_map["R2"]],
        },
        {
            "scenario_number": "S3",
            "title": "Marketplace item — route to seller",
            "customer_message": "I bought this from a marketplace seller and want to return it.",
            "scenario_type": "normal",
            "expected_action": "ROUTE_TO_SELLER",
            "expected_explanation": "Marketplace item must be routed to seller first",
            "risk_tier": "critical",
            "rule_ids_tested": [rule_map["R3"]],
        },
    ]
    created = []
    for sd in scenarios_data:
        s = Scenario(policy_id=policy.id, is_custom=False, **sd)
        db.add(s)
        created.append(s)
    await db.flush()
    return created


# ── Mini policy text used in fixtures ─────────────────────────────────────────

_SHOPFAST_MINI_POLICY = """
Section 1 — Standard Returns
Customers may return most items within 30 days of delivery for a full cash refund.

Section 2 — Final Sale Items
Items marked "Final Sale" are non-returnable. Exception: Final Sale items that
arrive damaged qualify for STORE CREDIT ONLY (not cash refund).

Section 3 — Marketplace Items
Agents must NOT approve direct refunds on marketplace items. Route to seller first.
"""
