from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from database import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id"), nullable=False
    )
    version_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # endpoint | batch_upload
    agent_endpoint_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | running | completed | failed
    started_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_scenarios: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    critical_violations: Mapped[int] = mapped_column(Integer, default=0)
    decision_accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="evaluation_runs")
    scenario_results: Mapped[list["ScenarioResult"]] = relationship(
        back_populates="evaluation_run"
    )
    findings: Mapped[list["Finding"]] = relationship(back_populates="evaluation_run")


class ScenarioResult(Base):
    __tablename__ = "scenario_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    agent_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # pass | fail | ambiguous | human_review
    evaluation_method: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # deterministic | llm_judge | human
    judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_severity: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # critical | major | minor
    violated_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_rules.id"), nullable=True
    )
    likely_cause: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # prompt | policy_ambiguity | tool | data | workflow
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    evaluation_run: Mapped["EvaluationRun"] = relationship(
        back_populates="scenario_results"
    )
    scenario: Mapped["Scenario"] = relationship(back_populates="results")
    findings: Mapped[list["Finding"]] = relationship(back_populates="scenario_result")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenario_results.id"), nullable=False
    )
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # critical | major | minor
    violated_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_rules.id"), nullable=True
    )
    violated_clause: Mapped[str | None] = mapped_column(Text, nullable=True)
    likely_cause: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open"
    )  # open | assigned | resolved | dismissed
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    scenario_result: Mapped["ScenarioResult"] = relationship(back_populates="findings")
    evaluation_run: Mapped["EvaluationRun"] = relationship(back_populates="findings")
    fix_assignments: Mapped[list["FixAssignment"]] = relationship(
        back_populates="finding"
    )


class FixAssignment(Base):
    __tablename__ = "fix_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id"), nullable=False
    )
    assignee: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # prompt | policy | tool | data | workflow
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open"
    )  # open | in_progress | completed
    assigned_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    finding: Mapped["Finding"] = relationship(back_populates="fix_assignments")
