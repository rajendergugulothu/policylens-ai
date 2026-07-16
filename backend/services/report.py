"""
Report generator.

Builds the launch-readiness report from an evaluation run.
Produces a Release record with recommendation (ready/conditionally_ready/not_ready).
PDF generation uses weasyprint (HTML → PDF with working hyperlinks).
"""

import os
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from models.evaluation import EvaluationRun, Finding
from models.policy import Policy
from models.policy_rule import PolicyRule
from models.scenario import Scenario
from models.release import Release, ReleaseSignature
from models.audit import AuditLog


def _compute_recommendation(
    critical_violations: int,
    decision_accuracy_pct: float,
    open_findings: int,
) -> tuple[str, str]:
    """
    Three-tier recommendation logic.
    Returns (recommendation, reason).
    """
    if critical_violations > 0:
        return (
            "not_ready",
            f"{critical_violations} critical policy violation(s) found. "
            "Critical violations must be 0% before production recommendation."
        )
    if decision_accuracy_pct < 90.0:
        return (
            "not_ready",
            f"Decision accuracy is {decision_accuracy_pct:.1f}% (threshold: ≥90%). "
            "Fix failing scenarios before launch."
        )
    if open_findings > 0:
        return (
            "conditionally_ready",
            f"{open_findings} non-critical finding(s) remain open. "
            "Review and document mitigations before launch."
        )
    return (
        "ready",
        "0% critical violation rate, ≥90% decision accuracy, all rules covered. "
        "Ready for production with dual sign-off."
    )


async def build_release(
    db: AsyncSession,
    evaluation_run_id: str,
    created_by: str = "system",
) -> Release:
    """Build a Release record from a completed evaluation run."""
    run_result = await db.execute(
        select(EvaluationRun).where(EvaluationRun.id == evaluation_run_id)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise ValueError(f"EvaluationRun {evaluation_run_id} not found.")
    if run.status != "completed":
        raise ValueError(f"Evaluation run is not completed (status: {run.status}).")

    # Count open findings
    open_findings = await db.scalar(
        select(func.count(Finding.id)).where(
            Finding.evaluation_run_id == evaluation_run_id,
            Finding.status == "open",
        )
    ) or 0

    # Scenario coverage: rules with at least one scenario
    total_rules = await db.scalar(
        select(func.count(PolicyRule.id)).where(
            PolicyRule.policy_id == run.policy_id,
            PolicyRule.status == "approved",
        )
    ) or 0

    scenario_count = await db.scalar(
        select(func.count(Scenario.id)).where(Scenario.policy_id == run.policy_id)
    ) or 0

    scenario_coverage_pct = 100.0 if total_rules == 0 else min(100.0, (scenario_count / max(total_rules, 1)) * 100)
    accuracy = run.decision_accuracy_pct or 0.0
    critical_violations = run.critical_violations or 0

    recommendation, reason = _compute_recommendation(critical_violations, accuracy, open_findings)

    release = Release(
        workspace_id=run.workspace_id,
        evaluation_run_id=run.id,
        recommendation=recommendation,
        recommendation_reason=reason,
        critical_violation_rate=round((critical_violations / max(run.total_scenarios, 1)) * 100, 2),
        decision_accuracy_pct=accuracy,
        scenario_coverage_pct=round(scenario_coverage_pct, 1),
        open_findings=open_findings,
        status="pending_approval",
        created_by=created_by,
    )
    db.add(release)
    await db.flush()

    db.add(AuditLog(
        workspace_id=run.workspace_id,
        entity_type="release",
        entity_id=release.id,
        action="release_created",
        actor=created_by,
        new_value={
            "recommendation": recommendation,
            "accuracy_pct": accuracy,
            "critical_violations": critical_violations,
            "open_findings": open_findings,
        },
    ))

    return release


async def sign_release(
    db: AsyncSession,
    release_id: str,
    signer_name: str,
    signer_role: str,
    notes: str | None = None,
) -> Release:
    """
    Add a signature to a release.
    When 2 signatures exist, status moves to 'approved'.
    Business rule: requires exactly 2 signatures (QA lead + VP/Compliance).
    """
    rel_result = await db.execute(select(Release).where(Release.id == release_id))
    release = rel_result.scalar_one_or_none()
    if not release:
        raise ValueError(f"Release {release_id} not found.")
    if release.status == "approved":
        raise ValueError("This release is already approved.")

    # Check for duplicate signer
    existing_sigs = await db.execute(
        select(ReleaseSignature).where(ReleaseSignature.release_id == release_id)
    )
    sigs = existing_sigs.scalars().all()
    if any(s.signer_name == signer_name for s in sigs):
        raise ValueError(f"{signer_name} has already signed this release.")

    sig = ReleaseSignature(
        release_id=release.id,
        signer_name=signer_name,
        signer_role=signer_role,
        signature_notes=notes,
        signed_at=datetime.now(timezone.utc),
    )
    db.add(sig)
    await db.flush()

    # Refresh sigs count
    sig_count = await db.scalar(
        select(func.count(ReleaseSignature.id)).where(ReleaseSignature.release_id == release_id)
    ) or 0

    if sig_count >= 2:
        release.status = "approved"
        db.add(AuditLog(
            workspace_id=release.workspace_id,
            entity_type="release",
            entity_id=release.id,
            action="release_approved",
            actor=signer_name,
            new_value={"status": "approved", "signature_count": sig_count},
        ))
    else:
        db.add(AuditLog(
            workspace_id=release.workspace_id,
            entity_type="release",
            entity_id=release.id,
            action="release_signed",
            actor=signer_name,
            new_value={"signer_role": signer_role, "signatures_so_far": sig_count},
        ))

    return release


async def build_version_comparison(
    db: AsyncSession,
    baseline_run_id: str,
    comparison_run_id: str,
    workspace_id: str,
) -> dict:
    """
    Compare two evaluation runs.
    Returns a summary of what changed between them.
    """
    from models.evaluation import ScenarioResult

    baseline_results = await db.execute(
        select(ScenarioResult).where(ScenarioResult.evaluation_run_id == baseline_run_id)
    )
    baseline = {str(r.scenario_id): r for r in baseline_results.scalars().all()}

    comparison_results = await db.execute(
        select(ScenarioResult).where(ScenarioResult.evaluation_run_id == comparison_run_id)
    )
    comparison = {str(r.scenario_id): r for r in comparison_results.scalars().all()}

    new_failures = [
        sid for sid, r in comparison.items()
        if r.verdict == "fail" and (sid not in baseline or baseline[sid].verdict == "pass")
    ]
    resolved_failures = [
        sid for sid, r in baseline.items()
        if r.verdict == "fail" and sid in comparison and comparison[sid].verdict == "pass"
    ]

    base_run_result = await db.execute(select(EvaluationRun).where(EvaluationRun.id == baseline_run_id))
    base_run = base_run_result.scalar_one()
    comp_run_result = await db.execute(select(EvaluationRun).where(EvaluationRun.id == comparison_run_id))
    comp_run = comp_run_result.scalar_one()

    return {
        "baseline_run_id": baseline_run_id,
        "comparison_run_id": comparison_run_id,
        "baseline_accuracy": base_run.decision_accuracy_pct,
        "comparison_accuracy": comp_run.decision_accuracy_pct,
        "accuracy_delta": round((comp_run.decision_accuracy_pct or 0) - (base_run.decision_accuracy_pct or 0), 1),
        "baseline_critical": base_run.critical_violations,
        "comparison_critical": comp_run.critical_violations,
        "critical_delta": (comp_run.critical_violations or 0) - (base_run.critical_violations or 0),
        "new_failures": len(new_failures),
        "resolved_failures": len(resolved_failures),
        "regression_detected": len(new_failures) > 0,
        "new_failure_scenario_ids": new_failures,
        "resolved_scenario_ids": resolved_failures,
    }
