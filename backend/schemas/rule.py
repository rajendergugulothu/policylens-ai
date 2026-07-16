from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Literal


Severity = Literal["critical", "high", "medium", "low"]
RuleStatus = Literal["pending_review", "approved", "rejected", "needs_resolution"]


class RuleRead(BaseModel):
    id: UUID
    policy_id: UUID
    rule_number: str
    condition: str
    action: str
    exception: str | None
    required_evidence: str | None
    source_section: str | None
    source_page: int | None
    source_citation_url: str | None
    notes: str | None  # stores source_citation_text from extraction
    severity: str
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    has_open_ambiguity: bool = False

    model_config = {"from_attributes": True}


class RuleApprove(BaseModel):
    reviewed_by: str = Field(..., example="priya.patel@clearpay.com")


class RuleEdit(BaseModel):
    """Edit a rule's condition, action, or exception before approving."""
    condition: str | None = None
    action: str | None = None
    exception: str | None = None
    required_evidence: str | None = None
    severity: Severity | None = None
    notes: str | None = None
    reviewed_by: str = Field(..., example="priya.patel@clearpay.com")


class RuleReject(BaseModel):
    reviewed_by: str
    notes: str = Field(..., min_length=10, example="This rule is covered by R3 and is a duplicate.")


class AmbiguityFlagRead(BaseModel):
    id: UUID
    rule_id: UUID
    flagged_clause: str
    flag_reason: str
    resolution: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    status: str

    model_config = {"from_attributes": True}


class AmbiguityResolve(BaseModel):
    """
    Written resolution of an ambiguous policy clause.
    Once submitted, the rule's status changes from 'needs_resolution'
    to 'pending_review' and scenario generation is unblocked for this rule.
    """
    resolution: str = Field(
        ...,
        min_length=20,
        example=(
            "Store credit applies only to the loyalty points portion of the purchase. "
            "The cash portion is refunded to the original payment method."
        ),
    )
    resolved_by: str = Field(..., example="sarah.chen@shopfast.com")


class ExtractionResponse(BaseModel):
    policy_id: UUID
    rules_extracted: int
    ambiguity_flags_created: int
    rules_needing_review: int
    message: str
