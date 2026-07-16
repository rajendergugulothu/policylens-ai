from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
from uuid import UUID

from database import get_db
from models.policy import Policy
from models.policy_rule import PolicyRule, AmbiguityFlag
from models.audit import AuditLog
from schemas.rule import (
    RuleRead, RuleApprove, RuleEdit, RuleReject,
    AmbiguityFlagRead, AmbiguityResolve, ExtractionResponse,
)
from services.extraction import extract_rules

router = APIRouter(prefix="/rules", tags=["rules"])


# ─── Extraction ───────────────────────────────────────────────────────────────

@router.post("/extract/{policy_id}", response_model=ExtractionResponse, status_code=201)
async def run_extraction(
    policy_id: UUID,
    actor: str = "system",
    db: AsyncSession = Depends(get_db),
):
    """
    Run LLM rule extraction on a policy.
    Calls Claude API, creates PolicyRule records (status=pending_review),
    and creates AmbiguityFlag records for non-deterministic clauses (FR-11).
    """
    # Check policy exists
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")

    # Check rules haven't already been extracted
    existing = await db.scalar(
        select(func.count(PolicyRule.id)).where(PolicyRule.policy_id == policy_id)
    )
    if existing and existing > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Rules already extracted ({existing} rules found). Delete existing rules before re-extracting.",
        )

    try:
        rules = await extract_rules(db, str(policy_id), actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Count ambiguity flags created
    ambiguity_count = await db.scalar(
        select(func.count(AmbiguityFlag.id))
        .join(PolicyRule, AmbiguityFlag.rule_id == PolicyRule.id)
        .where(PolicyRule.policy_id == policy_id, AmbiguityFlag.status == "open")
    ) or 0

    needs_resolution = sum(1 for r in rules if r.status == "needs_resolution")

    return ExtractionResponse(
        policy_id=policy_id,
        rules_extracted=len(rules),
        ambiguity_flags_created=ambiguity_count,
        rules_needing_review=len(rules) - needs_resolution,
        message=(
            f"Extracted {len(rules)} rules. "
            f"{ambiguity_count} ambiguity flag(s) require human resolution before testing. "
            f"{len(rules) - needs_resolution} rule(s) are ready for review."
        ),
    )


# ─── List rules ───────────────────────────────────────────────────────────────

@router.get("/policy/{policy_id}", response_model=list[RuleRead])
async def list_rules(
    policy_id: UUID,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all rules for a policy, optionally filtered by status."""
    query = select(PolicyRule).where(PolicyRule.policy_id == policy_id)
    if status:
        query = query.where(PolicyRule.status == status)
    query = query.order_by(PolicyRule.rule_number)

    result = await db.execute(query)
    rules = result.scalars().all()

    # Check which rules have open ambiguity flags
    if rules:
        rule_ids = [r.id for r in rules]
        flag_result = await db.execute(
            select(AmbiguityFlag.rule_id)
            .where(AmbiguityFlag.rule_id.in_(rule_ids), AmbiguityFlag.status == "open")
        )
        flagged_ids = {row.rule_id for row in flag_result}
    else:
        flagged_ids = set()

    output = []
    for rule in rules:
        item = RuleRead.model_validate(rule)
        item.has_open_ambiguity = rule.id in flagged_ids
        output.append(item)
    return output


@router.get("/{rule_id}", response_model=RuleRead)
async def get_rule(rule_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PolicyRule).where(PolicyRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")

    flag_count = await db.scalar(
        select(func.count(AmbiguityFlag.id))
        .where(AmbiguityFlag.rule_id == rule_id, AmbiguityFlag.status == "open")
    ) or 0

    item = RuleRead.model_validate(rule)
    item.has_open_ambiguity = flag_count > 0
    return item


# ─── Rule review actions ───────────────────────────────────────────────────────

@router.post("/{rule_id}/approve", response_model=RuleRead)
async def approve_rule(
    rule_id: UUID,
    payload: RuleApprove,
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a rule as the evaluation baseline.
    Blocked if the rule has open ambiguity flags.
    """
    rule = await _get_rule_or_404(db, rule_id)

    open_flags = await db.scalar(
        select(func.count(AmbiguityFlag.id))
        .where(AmbiguityFlag.rule_id == rule_id, AmbiguityFlag.status == "open")
    ) or 0

    if open_flags > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Rule has {open_flags} open ambiguity flag(s). Resolve them before approving.",
        )

    old_status = rule.status
    rule.status = "approved"
    rule.reviewed_by = payload.reviewed_by
    rule.reviewed_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        workspace_id=(await _get_workspace_id(db, rule)),
        entity_type="policy_rule",
        entity_id=rule.id,
        action="rule_approved",
        actor=payload.reviewed_by,
        old_value={"status": old_status},
        new_value={"status": "approved"},
    ))

    item = RuleRead.model_validate(rule)
    item.has_open_ambiguity = False
    return item


@router.post("/{rule_id}/edit", response_model=RuleRead)
async def edit_and_approve_rule(
    rule_id: UUID,
    payload: RuleEdit,
    db: AsyncSession = Depends(get_db),
):
    """
    Edit rule fields and approve in a single step.
    Useful when the extracted rule needs refinement before becoming the baseline.
    """
    rule = await _get_rule_or_404(db, rule_id)

    old_values = {
        "condition": rule.condition,
        "action": rule.action,
        "exception": rule.exception,
        "severity": rule.severity,
        "status": rule.status,
    }

    if payload.condition is not None:
        rule.condition = payload.condition
    if payload.action is not None:
        rule.action = payload.action
    if payload.exception is not None:
        rule.exception = payload.exception
    if payload.required_evidence is not None:
        rule.required_evidence = payload.required_evidence
    if payload.severity is not None:
        rule.severity = payload.severity
    if payload.notes is not None:
        rule.notes = payload.notes

    rule.status = "approved"
    rule.reviewed_by = payload.reviewed_by
    rule.reviewed_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        workspace_id=(await _get_workspace_id(db, rule)),
        entity_type="policy_rule",
        entity_id=rule.id,
        action="rule_edited",
        actor=payload.reviewed_by,
        old_value=old_values,
        new_value={
            "condition": rule.condition,
            "action": rule.action,
            "severity": rule.severity,
            "status": "approved",
        },
    ))

    item = RuleRead.model_validate(rule)
    item.has_open_ambiguity = False
    return item


@router.post("/{rule_id}/reject", response_model=RuleRead)
async def reject_rule(
    rule_id: UUID,
    payload: RuleReject,
    db: AsyncSession = Depends(get_db),
):
    """Reject a rule (e.g. duplicate, misextracted). Requires a comment."""
    rule = await _get_rule_or_404(db, rule_id)

    old_status = rule.status
    rule.status = "rejected"
    rule.reviewed_by = payload.reviewed_by
    rule.reviewed_at = datetime.now(timezone.utc)
    rule.notes = payload.notes

    db.add(AuditLog(
        workspace_id=(await _get_workspace_id(db, rule)),
        entity_type="policy_rule",
        entity_id=rule.id,
        action="rule_rejected",
        actor=payload.reviewed_by,
        old_value={"status": old_status},
        new_value={"status": "rejected", "notes": payload.notes},
    ))

    item = RuleRead.model_validate(rule)
    item.has_open_ambiguity = False
    return item


# ─── Ambiguity flags (FR-11) ─────────────────────────────────────────────────

@router.get("/ambiguity/policy/{policy_id}", response_model=list[AmbiguityFlagRead])
async def list_ambiguity_flags(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all open ambiguity flags for a policy. These block scenario generation."""
    result = await db.execute(
        select(AmbiguityFlag)
        .join(PolicyRule, AmbiguityFlag.rule_id == PolicyRule.id)
        .where(PolicyRule.policy_id == policy_id, AmbiguityFlag.status == "open")
        .order_by(AmbiguityFlag.created_at)
    )
    return result.scalars().all()


@router.post("/ambiguity/{flag_id}/resolve", response_model=AmbiguityFlagRead)
async def resolve_ambiguity(
    flag_id: UUID,
    payload: AmbiguityResolve,
    db: AsyncSession = Depends(get_db),
):
    """
    Resolve an ambiguity flag by writing the intended behavior in plain language.
    This unblocks scenario generation for the associated rule.

    After resolution:
    - AmbiguityFlag.status → 'resolved'
    - PolicyRule.status → 'pending_review' (ready for human approval)
    """
    result = await db.execute(
        select(AmbiguityFlag).where(AmbiguityFlag.id == flag_id)
    )
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=404, detail="Ambiguity flag not found.")
    if flag.status == "resolved":
        raise HTTPException(status_code=409, detail="This flag is already resolved.")

    flag.resolution = payload.resolution
    flag.resolved_by = payload.resolved_by
    flag.resolved_at = datetime.now(timezone.utc)
    flag.status = "resolved"

    # Unblock the rule — move to pending_review so it can be approved
    rule_result = await db.execute(
        select(PolicyRule).where(PolicyRule.id == flag.rule_id)
    )
    rule = rule_result.scalar_one()
    rule.status = "pending_review"
    rule.notes = (rule.notes or "") + f"\n\nAmbiguity resolved: {payload.resolution}"

    db.add(AuditLog(
        workspace_id=(await _get_workspace_id(db, rule)),
        entity_type="ambiguity_flag",
        entity_id=flag.id,
        action="ambiguity_resolved",
        actor=payload.resolved_by,
        old_value={"status": "open"},
        new_value={"status": "resolved", "resolution": payload.resolution},
    ))

    return flag


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_rule_or_404(db: AsyncSession, rule_id: UUID) -> PolicyRule:
    result = await db.execute(select(PolicyRule).where(PolicyRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    return rule


async def _get_workspace_id(db: AsyncSession, rule: PolicyRule) -> UUID:
    result = await db.execute(
        select(Policy.workspace_id).where(Policy.id == rule.policy_id)
    )
    return result.scalar_one()
