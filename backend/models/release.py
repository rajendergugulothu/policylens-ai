from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from database import Base


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False
    )
    recommendation: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # ready | conditionally_ready | not_ready
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    critical_violation_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    scenario_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_findings: Mapped[int] = mapped_column(Integer, default=0)
    report_pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft"
    )  # draft | pending_approval | approved | rejected
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="releases")
    signatures: Mapped[list["ReleaseSignature"]] = relationship(
        back_populates="release"
    )


class ReleaseSignature(Base):
    """
    Dual sign-off requirement (v2.0 — from Sarah Chen design partner session).
    A release requires exactly 2 signatures before moving to 'approved'.
    """

    __tablename__ = "release_signatures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("releases.id"), nullable=False
    )
    signer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_role: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # qa_lead | vp_operations | compliance_officer | head_of_ai | other
    signature_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    release: Mapped["Release"] = relationship(back_populates="signatures")
