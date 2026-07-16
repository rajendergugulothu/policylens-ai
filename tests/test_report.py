"""
Tests for services/report.py

Covers:
- _compute_recommendation(): all three tiers (not_ready, conditionally_ready, ready)
- build_release(): creates Release from completed EvaluationRun
- sign_release(): dual sign-off, status → approved on second signature,
  blocks duplicate signer, blocks signing already-approved release
- build_version_comparison(): accuracy delta, new/resolved failure counts, regression flag
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select


# ── _compute_recommendation ────────────────────────────────────────────────────

class TestComputeRecommendation:
    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from services.report import _compute_recommendation
        self.compute = _compute_recommendation

    def test_not_ready_when_critical_violations(self):
        rec, reason = self.compute(critical_violations=2, decision_accuracy_pct=95.0, open_findings=0)
        assert rec == "not_ready"
        assert "critical" in reason.lower()

    def test_not_ready_when_accuracy_below_threshold(self):
        rec, reason = self.compute(critical_violations=0, decision_accuracy_pct=88.5, open_findings=0)
        assert rec == "not_ready"
        assert "88.5" in reason

    def test_not_ready_critical_takes_priority_over_accuracy(self):
        rec, _ = self.compute(critical_violations=1, decision_accuracy_pct=50.0, open_findings=3)
        assert rec == "not_ready"

    def test_conditionally_ready_when_open_findings(self):
        rec, reason = self.compute(critical_violations=0, decision_accuracy_pct=92.0, open_findings=3)
        assert rec == "conditionally_ready"
        assert "3" in reason

    def test_ready_when_all_thresholds_met(self):
        rec, _ = self.compute(critical_violations=0, decision_accuracy_pct=100.0, open_findings=0)
        assert rec == "ready"

    def test_ready_at_exactly_90_percent(self):
        rec, _ = self.compute(critical_violations=0, decision_accuracy_pct=90.0, open_findings=0)
        assert rec == "ready"

    def test_not_ready_at_89_point_9_percent(self):
        rec, _ = self.compute(critical_violations=0, decision_accuracy_pct=89.9, open_findings=0)
        assert rec == "not_ready"


# ── Fixtures for release tests ─────────────────────────────────────────────────

async def _make_completed_run(db, policy, scenarios, *, passed, failed, critical):
    from models.evaluation import EvaluationRun
    total = passed + failed
    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="test",
        agent_type="batch_upload",
        status="completed",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_scenarios=total,
        passed=passed,
        failed=failed,
        critical_violations=critical,
        decision_accuracy_pct=round((passed / total) * 100, 1) if total else 0.0,
    )
    db.add(run)
    await db.flush()
    return run


# ── build_release ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_release_creates_record(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release
    from models.release import Release

    run = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)
    release = await build_release(db, str(run.id), created_by="test")

    assert release is not None
    assert release.recommendation == "ready"
    assert release.status == "pending_approval"
    assert release.decision_accuracy_pct == 100.0


@pytest.mark.asyncio
async def test_build_release_not_ready_on_critical(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release

    run = await _make_completed_run(db, policy, scenarios, passed=2, failed=1, critical=1)
    release = await build_release(db, str(run.id))

    assert release.recommendation == "not_ready"


@pytest.mark.asyncio
async def test_build_release_fails_for_incomplete_run(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release
    from models.evaluation import EvaluationRun

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="pending",
        agent_type="batch_upload",
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    with pytest.raises(ValueError, match="not completed"):
        await build_release(db, str(run.id))


@pytest.mark.asyncio
async def test_build_release_fails_for_missing_run(db):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release

    with pytest.raises(ValueError, match="not found"):
        await build_release(db, "00000000-0000-0000-0000-000000000000")


# ── sign_release ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_signature_keeps_pending(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release, sign_release

    run = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)
    release = await build_release(db, str(run.id))

    release = await sign_release(db, str(release.id), "Alice", "qa_lead")
    assert release.status == "pending_approval"


@pytest.mark.asyncio
async def test_second_signature_approves_release(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release, sign_release

    run = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)
    release = await build_release(db, str(run.id))

    await sign_release(db, str(release.id), "Alice", "qa_lead")
    release = await sign_release(db, str(release.id), "Bob", "vp_operations")
    assert release.status == "approved"


@pytest.mark.asyncio
async def test_duplicate_signer_raises(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release, sign_release

    run = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)
    release = await build_release(db, str(run.id))

    await sign_release(db, str(release.id), "Alice", "qa_lead")
    with pytest.raises(ValueError, match="already signed"):
        await sign_release(db, str(release.id), "Alice", "qa_lead")


@pytest.mark.asyncio
async def test_signing_approved_release_raises(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_release, sign_release

    run = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)
    release = await build_release(db, str(run.id))

    await sign_release(db, str(release.id), "Alice", "qa_lead")
    await sign_release(db, str(release.id), "Bob", "vp_operations")

    with pytest.raises(ValueError, match="already approved"):
        await sign_release(db, str(release.id), "Carol", "compliance")


# ── build_version_comparison ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_version_compare_accuracy_delta(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_version_comparison

    baseline = await _make_completed_run(db, policy, scenarios, passed=2, failed=1, critical=1)
    comparison = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)

    result = await build_version_comparison(db, str(baseline.id), str(comparison.id), str(policy.workspace_id))

    assert result["accuracy_delta"] == pytest.approx(33.4, abs=1.0)
    assert result["critical_delta"] == -1


@pytest.mark.asyncio
async def test_version_compare_regression_detected(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_version_comparison
    from models.evaluation import EvaluationRun, ScenarioResult

    baseline = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)
    comparison = await _make_completed_run(db, policy, scenarios, passed=2, failed=1, critical=0)

    # Add a pass result in baseline and a fail in comparison for the same scenario
    db.add(ScenarioResult(
        evaluation_run_id=baseline.id,
        scenario_id=scenarios[0].id,
        agent_response="I'll process a full refund.",
        verdict="pass",
        evaluation_method="deterministic",
    ))
    db.add(ScenarioResult(
        evaluation_run_id=comparison.id,
        scenario_id=scenarios[0].id,
        agent_response="Sorry, I cannot help.",
        verdict="fail",
        evaluation_method="llm_judge",
        failure_severity="major",
    ))
    await db.flush()

    result = await build_version_comparison(db, str(baseline.id), str(comparison.id), str(policy.workspace_id))

    assert result["regression_detected"] is True
    assert result["new_failures"] >= 1


@pytest.mark.asyncio
async def test_version_compare_resolved_failures(db, policy, approved_rules, scenarios):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.report import build_version_comparison
    from models.evaluation import EvaluationRun, ScenarioResult

    baseline = await _make_completed_run(db, policy, scenarios, passed=2, failed=1, critical=1)
    comparison = await _make_completed_run(db, policy, scenarios, passed=3, failed=0, critical=0)

    # A scenario that failed in baseline but passes in comparison
    db.add(ScenarioResult(
        evaluation_run_id=baseline.id,
        scenario_id=scenarios[1].id,
        agent_response="Wrong response.",
        verdict="fail",
        evaluation_method="llm_judge",
        failure_severity="critical",
    ))
    db.add(ScenarioResult(
        evaluation_run_id=comparison.id,
        scenario_id=scenarios[1].id,
        agent_response="I'm issuing store credit to your account.",
        verdict="pass",
        evaluation_method="deterministic",
    ))
    await db.flush()

    result = await build_version_comparison(db, str(baseline.id), str(comparison.id), str(policy.workspace_id))

    assert result["resolved_failures"] >= 1
    assert result["regression_detected"] is False or result["new_failures"] == 0
