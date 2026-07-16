"""
ShopFast Simulated Agent — for PolicyLens demo.

Represents a typical LLM-powered customer service agent that has NOT been
grounded in the specific ShopFast v4.2 policy. It uses general-purpose
reasoning and gets common cases right, but fails on the specific edge cases
that PolicyLens is designed to catch.

Run standalone:  uvicorn demo.simulated_agent:app --port 8001
Or import:       from demo.simulated_agent import get_agent_response
"""

import re
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="ShopFast Simulated Agent", version="1.0.0")


class AgentRequest(BaseModel):
    message: str


class AgentResponse(BaseModel):
    response: str


# ─── Core agent logic ─────────────────────────────────────────────────────────

async def get_agent_response(customer_message: str) -> str:
    """
    Simulated agent response. Gets standard cases right but fails on
    the four specific edge cases from the concierge test.
    """
    msg = customer_message.lower()

    # ── VIOLATION 1: Final Sale + Damaged → wrongly issues cash refund ──────
    # Policy: Final Sale damaged items → STORE CREDIT ONLY (Section 2 exception)
    # Agent error: treats "damaged" as triggering normal damaged-item cash refund
    if _is_final_sale(msg) and _is_damaged(msg):
        return (
            "I'm sorry to hear your item arrived damaged! Even though it was marked "
            "Final Sale, since it arrived in damaged condition, you're entitled to a "
            "full cash refund back to your original payment method. I'll process that "
            "right away — please send us a photo of the damage within 5 days. "
            "You should see the refund in 3-5 business days."
        )

    # ── VIOLATION 2: Apple + Holiday → uses Jan 31 instead of Jan 15 ────────
    # Policy: Apple products holiday extension deadline is Jan 15, not Jan 31
    # Agent error: applies the standard Jan 31 deadline to Apple products
    if _is_apple_product(msg) and _is_holiday_return(msg):
        return (
            "Great news! Since your Apple product was purchased during the holiday "
            "season (November–December), you're covered by our Holiday Return Extension. "
            "You have until January 31 to return it for a full refund. Just make sure "
            "the item is in its original condition and packaging. Would you like me to "
            "start the return process now?"
        )

    # ── VIOLATION 3: Marketplace item → wrongly processes direct refund ──────
    # Policy: Marketplace items must be routed to seller first (Section 4)
    # Agent error: processes refund directly, skipping seller routing
    if _is_marketplace_item(msg) and _wants_return_or_refund(msg):
        if _is_damaged(msg):
            return (
                "I can see this was a Marketplace purchase. Since the item arrived "
                "damaged, I'll go ahead and process a full refund for you directly — "
                "no need to contact the seller. The refund of the full purchase amount "
                "will be returned to your original payment method within 3-5 business days."
            )
        return (
            "I can help you with that return! Even though this was purchased from one "
            "of our Marketplace partners, I can process the refund directly for you as "
            "a courtesy. You'll receive a full refund to your original payment method "
            "within 3-5 business days. No need to contact the seller separately."
        )

    # ── VIOLATION 4: Loyalty points purchase → issues all as cash ────────────
    # Policy: Must split — cash portion → cash refund, points portion → store credit
    # Agent error: issues entire refund as cash for simplicity
    if _is_loyalty_points_purchase(msg) and _wants_return_or_refund(msg):
        return (
            "I can process that refund for you! I'll issue the full refund amount back "
            "to your original payment method as a cash refund — that's the easiest way "
            "to handle it. You should see $" + _extract_amount(customer_message) + " "
            "back on your card within 3-5 business days. Is there anything else I can help you with?"
        )

    # ── VIOLATION 5: Sympathetic late return → incorrectly approves ──────────
    # Policy: 30-day return window is strict from delivery date
    # Agent error: approves out-of-window returns when customer gives sympathetic reason
    if _is_late_return(msg) and _has_sympathetic_reason(msg):
        return (
            "I completely understand — life happens, and I'm sorry you're going through "
            "a difficult time. Even though it's been more than 30 days, I'm going to "
            "make a one-time exception and process this return for you. I'll issue a "
            "full refund to your original payment method. You'll receive a prepaid "
            "return label via email shortly."
        )

    # ── CORRECT: Standard return within window ────────────────────────────────
    if _is_standard_return(msg) and not _is_late_return(msg):
        return (
            "I'd be happy to help with your return! Since your item is within the 30-day "
            "return window and in original condition, you qualify for a full cash refund. "
            "I'll send you a prepaid return label — once we receive the item, your refund "
            "will be processed within 3-5 business days."
        )

    # ── CORRECT: Non-returnable category ─────────────────────────────────────
    if _is_non_returnable(msg) and not _is_damaged(msg):
        return (
            "I'm sorry, but this item falls into our non-returnable category "
            "(digital downloads, perishables, personalized items, or intimate apparel). "
            "Unfortunately, we're unable to accept a return on this purchase. "
            "If the item arrived damaged or defective, please contact us within 7 days "
            "with photos and we'll make it right."
        )

    # ── CORRECT: Damaged standard item → cash refund or replacement ──────────
    if _is_damaged(msg) and not _is_final_sale(msg) and not _is_marketplace_item(msg):
        return (
            "I'm really sorry your item arrived damaged! That's not acceptable. "
            "You have two options: a full cash refund to your original payment method, "
            "or a free replacement sent to you right away — your choice. "
            "Please send us a photo of the damage within 7 days and we'll take care "
            "of this immediately."
        )

    # ── CORRECT: Final Sale, no damage → deny ────────────────────────────────
    if _is_final_sale(msg) and not _is_damaged(msg):
        return (
            "I'm sorry, but items marked as Final Sale at checkout are non-returnable "
            "and non-refundable per our policy. This applies to clearance items under $5, "
            "trading card products, and limited-edition drops. If your item arrived "
            "damaged or defective, please contact us within 5 days with a photo and "
            "we can offer store credit."
        )

    # ── CORRECT: Strict late return, no sympathy ──────────────────────────────
    if _is_late_return(msg) and not _has_sympathetic_reason(msg):
        return (
            "I'm sorry, but our return window is 30 days from the delivery date, "
            "and it looks like that window has closed for your order. Unfortunately, "
            "we're unable to process a return at this time. If there's an issue with "
            "the item's condition or quality, please let me know and I'll see what "
            "options are available."
        )

    # ── DEFAULT: Request clarification ───────────────────────────────────────
    return (
        "I'd be happy to help with your order! Could you provide a bit more detail "
        "about what happened and what resolution you're looking for? For example, "
        "was the item damaged, or are you simply wanting to return it? "
        "Also, when did you receive the order?"
    )


# ─── Pattern matchers ─────────────────────────────────────────────────────────

def _is_final_sale(msg: str) -> bool:
    return bool(re.search(r"final sale|clearance|trading card|limited.?edition", msg))

def _is_damaged(msg: str) -> bool:
    return bool(re.search(r"damage|defect|broken|cracked|wrong item|not as described|different from", msg))

def _is_apple_product(msg: str) -> bool:
    return bool(re.search(r"\bapple\b|iphone|ipad|macbook|airpods|apple watch", msg))

def _is_holiday_return(msg: str) -> bool:
    return bool(re.search(r"holiday|christmas|november|december|holiday extension|jan(uary)?", msg))

def _is_marketplace_item(msg: str) -> bool:
    return bool(re.search(r"marketplace|third.?party|seller|sold by", msg))

def _is_loyalty_points_purchase(msg: str) -> bool:
    return bool(re.search(r"loyalty point|points.*paid|paid.*points|reward point|point.*purchase", msg))

def _is_late_return(msg: str) -> bool:
    return bool(re.search(r"(3[1-9]|[4-9]\d|\d{3,})\s*day|over a month|couple months|been a while|past.*window|outside.*window|expired|too late", msg))

def _has_sympathetic_reason(msg: str) -> bool:
    return bool(re.search(r"hospital|sick|death|funeral|emergency|surgery|accident|ill|passing|bereave|tragedy|difficult time|family member", msg))

def _is_standard_return(msg: str) -> bool:
    return bool(re.search(r"return|refund|send back|exchange", msg))

def _wants_return_or_refund(msg: str) -> bool:
    return bool(re.search(r"return|refund|send back|exchange|money back", msg))

def _is_non_returnable(msg: str) -> bool:
    return bool(re.search(r"digital|download|software|perishable|custom|personali[sz]|swimwear|underwear|intimate", msg))

def _extract_amount(msg: str) -> str:
    match = re.search(r"\$?([\d,]+\.?\d*)", msg)
    return match.group(1) if match else "the full amount"


# ─── FastAPI endpoint ─────────────────────────────────────────────────────────

@app.post("/agent/respond", response_model=AgentResponse)
async def respond(request: AgentRequest):
    """Endpoint used by PolicyLens evaluation engine in endpoint mode."""
    response = await get_agent_response(request.message)
    return AgentResponse(response=response)


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "shopfast-simulated", "version": "1.0.0"}
