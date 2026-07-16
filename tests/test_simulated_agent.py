"""
Tests for demo/simulated_agent.py

Validates that the agent:
- Gets standard cases right (realistic)
- Produces the four specific policy violations that PolicyLens is designed to catch
- Returns a string response from get_agent_response()
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def agent():
    from demo.simulated_agent import get_agent_response
    return get_agent_response


# ── Correct behaviours (agent should pass these) ──────────────────────────────

@pytest.mark.asyncio
async def test_standard_return_approved(agent):
    response = await agent("I want to return my jacket, I got it 15 days ago and it's unused.")
    assert any(word in response.lower() for word in ["refund", "return", "process"])


@pytest.mark.asyncio
async def test_final_sale_no_damage_denied(agent):
    response = await agent("I want to return this Final Sale clearance item I bought last week.")
    assert any(word in response.lower() for word in ["final sale", "non-returnable", "cannot", "not accept"])


@pytest.mark.asyncio
async def test_damaged_standard_item_gets_refund_or_replacement(agent):
    response = await agent("My new blender arrived completely cracked. I want to return it.")
    assert any(word in response.lower() for word in ["refund", "replacement", "replace"])


@pytest.mark.asyncio
async def test_response_is_string(agent):
    response = await agent("Hello, I need help with my order.")
    assert isinstance(response, str)
    assert len(response) > 10


# ── Violation 1: Final Sale + damaged → agent wrongly issues cash refund ──────

@pytest.mark.asyncio
async def test_final_sale_damaged_violation_cash_refund(agent):
    """
    POLICY: Final Sale damaged → STORE CREDIT ONLY
    AGENT BUG: Issues cash refund instead
    """
    response = await agent(
        "I bought a Final Sale trading card set and it arrived with damaged packaging. "
        "I want a cash refund please."
    )
    # Agent should say "cash refund" (the violation)
    assert "cash" in response.lower() or "refund" in response.lower()
    # Agent should NOT correctly restrict to store credit
    assert "store credit only" not in response.lower()


# ── Violation 2: Apple + holiday → agent uses Jan 31 instead of Jan 15 ────────

@pytest.mark.asyncio
async def test_apple_holiday_violation_wrong_deadline(agent):
    """
    POLICY: Apple products holiday extension deadline is January 15
    AGENT BUG: Tells customer January 31
    """
    response = await agent(
        "I got an Apple iPhone for Christmas (bought in December) and want to return it. "
        "Is the holiday return extension still valid?"
    )
    assert "january 31" in response.lower() or "jan 31" in response.lower()
    assert "january 15" not in response.lower() and "jan 15" not in response.lower()


# ── Violation 3: Marketplace item → agent processes direct refund ─────────────

@pytest.mark.asyncio
async def test_marketplace_violation_direct_refund(agent):
    """
    POLICY: Marketplace items must be routed to seller first
    AGENT BUG: Processes refund directly
    """
    response = await agent(
        "I bought a laptop from a third-party seller on ShopFast Marketplace "
        "and want to return it. Can you process my refund?"
    )
    # Agent should process refund directly (the violation)
    assert "refund" in response.lower()
    # Agent should NOT route to seller
    assert "contact the seller" not in response.lower() or "route" not in response.lower()


# ── Violation 4: Loyalty points → agent issues all as cash ───────────────────

@pytest.mark.asyncio
async def test_loyalty_points_violation_full_cash(agent):
    """
    POLICY: Loyalty points purchase → split refund (cash + store credit)
    AGENT BUG: Issues full amount as cash
    """
    response = await agent(
        "I paid for my order using $30 cash and 500 loyalty points. "
        "The item doesn't fit and I'd like a refund of the $75 total."
    )
    # Agent should issue full cash (the violation)
    assert "cash" in response.lower() or "payment method" in response.lower()
    # Agent should NOT split into cash + store credit
    assert "store credit" not in response.lower()


# ── Violation 5: Sympathetic late return → agent incorrectly approves ─────────

@pytest.mark.asyncio
async def test_sympathetic_late_return_violation(agent):
    """
    POLICY: 30-day window is strict
    AGENT BUG: Approves return when customer gives sympathetic reason
    """
    response = await agent(
        "I know it's been 45 days but I was in the hospital for surgery "
        "and couldn't deal with this return. Can you please make an exception?"
    )
    # Agent should approve the late return (the violation)
    assert any(word in response.lower() for word in ["exception", "return", "refund", "process"])
    assert "cannot" not in response.lower() and "sorry" not in response.lower()
