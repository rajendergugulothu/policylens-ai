"""
Tests for services/evaluator.py

Covers:
- _check_deterministic(): keyword matching, contradiction detection, ambiguous fallthrough
- run_evaluation(): pass/fail tracking, critical violation counting, accuracy calc,
  LLM judge invocation for critical-tier scenarios, Finding record creation
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select


# ── _check_deterministic ───────────────────────────────────────────────────────

class TestCheckDeterministic:
    """Unit tests for the keyword-based deterministic checker."""

    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from services.evaluator import _check_deterministic
        self.check = _check_deterministic

    def test_approve_full_refund_detected(self):
        verdict, _ = self.check("APPROVE_FULL_REFUND", "I'll process a full refund for you right away.")
        assert verdict == "pass"

    def test_approve_store_credit_detected(self):
        verdict, _ = self.check("APPROVE_STORE_CREDIT", "I'm issuing store credit to your account.")
        assert verdict == "pass"

    def test_route_to_seller_detected(self):
        verdict, _ = self.check("ROUTE_TO_SELLER", "I'll contact the seller on your behalf.")
        assert verdict == "pass"

    def test_deny_return_detected(self):
        verdict, _ = self.check("DENY_RETURN", "This item is final sale and not eligible for return.")
        assert verdict == "pass"

    def test_request_evidence_detected(self):
        verdict, _ = self.check("REQUEST_EVIDENCE", "Please send us a photo of the damage.")
        assert verdict == "pass"

    def test_approve_when_deny_expected_is_fail(self):
        verdict, explanation = self.check(
            "DENY_RETURN",
            "I'm happy to approve a full refund for you!",
        )
        assert verdict == "fail"
        assert "approve" in explanation.lower() or "DENY" in explanation

    def test_deny_when_approve_expected_is_fail(self):
        verdict, explanation = self.check(
            "APPROVE_FULL_REFUND",
            "Sorry, I cannot process this return — you are not eligible.",
        )
        assert verdict == "fail"

    def test_no_match_returns_ambiguous(self):
        verdict, _ = self.check("APPROVE_FULL_REFUND", "Let me look into your order details.")
        assert verdict == "ambiguous"

    def test_replacement_detected(self):
        verdict, _ = self.check("APPROVE_REPLACEMENT", "We'll send a replacement to you right away.")
        assert verdict == "pass"

    def test_escalate_detected(self):
        verdict, _ = self.check("ESCALATE_TO_CS", "I'm escalating this to our specialist team.")
        assert verdict == "pass"


# ── run_evaluation ─────────────────────────────────────────────────────────────

def _make_judge_pass():
    content = MagicMock()
    content.text = json.dumps({
        "verdict": "pass",
        "failure_severity": None,
        "violated_rule_number": None,
        "likely_cause": None,
        "explanation": "Agent correctly applied the policy.",
    })
    msg = MagicMock()
    msg.content = [content]
    return msg


def _make_judge_fail(severity="critical", rule_number="R2", cause="prompt"):
    content = MagicMock()
    content.text = json.dumps({
        "verdict": "fail",
        "failure_severity": severity,
        "violated_rule_number": rule_number,
        "likely_cause": cause,
        "explanation": "Agent issued cash refund instead of store credit on Final Sale item.",
    })
    msg = MagicMock()
    msg.content = [content]
    return msg


@pytest.mark.asyncio
async def test_all_pass_sets_100_accuracy(db, policy, approved_rules, scenarios):
    """When every scenario passes, accuracy = 100% and critical_violations = 0."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.evaluator import run_evaluation
    from models.evaluation import EvaluationRun
    from datetime import datetime, timezone

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="test-v1",
        agent_type="batch_upload",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    batch = {
        str(scenarios[0].id): "I'll process a full refund for you right away.",
        str(scenarios[1].id): "I'm issuing store credit to your account.",
        str(scenarios[2].id): "I'll contact the seller on your behalf.",
    }

    with patch("services.evaluator.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_judge_pass())
        result = await run_evaluation(db, str(run.id), batch_responses=batch)

    assert result.status == "completed"
    assert result.passed == 3
    assert result.failed == 0
    assert result.critical_violations == 0
    assert result.decision_accuracy_pct == 100.0


@pytest.mark.asyncio
async def test_critical_failure_counted(db, policy, approved_rules, scenarios):
    """A critical-tier scenario failure increments critical_violations."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.evaluator import run_evaluation
    from models.evaluation import EvaluationRun
    from datetime import datetime, timezone

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="test-v2",
        agent_type="batch_upload",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    # S2 is critical-tier; agent wrongly issues cash refund (triggers LLM judge)
    batch = {
        str(scenarios[0].id): "I'll process a full refund for you right away.",
        str(scenarios[1].id): "I'll give you a full cash refund since the item was damaged.",
        str(scenarios[2].id): "I'll contact the seller on your behalf.",
    }

    with patch("services.evaluator.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_judge_fail("critical", "R2"))
        result = await run_evaluation(db, str(run.id), batch_responses=batch)

    assert result.critical_violations >= 1


@pytest.mark.asyncio
async def test_finding_created_for_failure(db, policy, approved_rules, scenarios):
    """A Finding record is created when a scenario fails."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.evaluator import run_evaluation
    from models.evaluation import EvaluationRun, Finding
    from datetime import datetime, timezone

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="test-v3",
        agent_type="batch_upload",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    batch = {
        str(scenarios[0].id): "I'll process a full refund for you right away.",
        str(scenarios[1].id): "Here is your cash refund.",
        str(scenarios[2].id): "I'll contact the seller on your behalf.",
    }

    with patch("services.evaluator.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_judge_fail("critical", "R2"))
        await run_evaluation(db, str(run.id), batch_responses=batch)

    findings_result = await db.execute(
        select(Finding).where(Finding.evaluation_run_id == run.id)
    )
    findings = findings_result.scalars().all()
    assert len(findings) >= 1
    assert findings[0].status == "open"
    assert findings[0].severity in ("critical", "major", "minor")


@pytest.mark.asyncio
async def test_accuracy_calculation(db, policy, approved_rules, scenarios):
    """Decision accuracy = passed / total * 100, rounded to 1 decimal."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.evaluator import run_evaluation
    from models.evaluation import EvaluationRun
    from datetime import datetime, timezone

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="test-v4",
        agent_type="batch_upload",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    # 2 of 3 pass → 66.7%
    batch = {
        str(scenarios[0].id): "I'll process a full refund for you right away.",
        str(scenarios[1].id): "Here is your cash refund.",  # will fail
        str(scenarios[2].id): "I'll contact the seller on your behalf.",
    }

    with patch("services.evaluator.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_judge_fail("major", "R2"))
        result = await run_evaluation(db, str(run.id), batch_responses=batch)

    assert result.total_scenarios == 3
    assert result.decision_accuracy_pct == pytest.approx(66.7, abs=1.0)


@pytest.mark.asyncio
async def test_missing_batch_response_treated_as_no_response(db, policy, approved_rules, scenarios):
    """Scenarios with no batch response get a placeholder and are evaluated."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.evaluator import run_evaluation
    from models.evaluation import EvaluationRun, ScenarioResult
    from datetime import datetime, timezone

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="test-v5",
        agent_type="batch_upload",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    # Only provide response for S1; S2 and S3 get no response
    batch = {str(scenarios[0].id): "I'll process a full refund for you right away."}

    with patch("services.evaluator.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_judge_fail("minor", "R1"))
        result = await run_evaluation(db, str(run.id), batch_responses=batch)

    assert result.total_scenarios == 3

    results_q = await db.execute(
        select(ScenarioResult).where(ScenarioResult.evaluation_run_id == run.id)
    )
    results = results_q.scalars().all()
    no_response = [r for r in results if "[No response" in (r.agent_response or "")]
    assert len(no_response) == 2


@pytest.mark.asyncio
async def test_critical_tier_always_uses_llm_judge(db, policy, approved_rules, scenarios):
    """Critical-tier scenarios always go to the LLM judge regardless of deterministic result."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.evaluator import run_evaluation
    from models.evaluation import EvaluationRun
    from datetime import datetime, timezone

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=policy.id,
        version_label="test-v6",
        agent_type="batch_upload",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    # S2 and S3 are critical — even if deterministic matches, LLM judge should be called
    batch = {
        str(scenarios[0].id): "I'll process a full refund for you right away.",
        str(scenarios[1].id): "I'm issuing store credit to your account.",
        str(scenarios[2].id): "I'll contact the seller on your behalf.",
    }

    with patch("services.evaluator.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=_make_judge_pass())
        await run_evaluation(db, str(run.id), batch_responses=batch)
        # Should have been called for S2 and S3 (both critical)
        assert mock_client.messages.create.call_count >= 2
