from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from database import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id"), nullable=False
    )
    scenario_number: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_message: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # normal | edge | exception | adversarial
    rule_ids_tested: Mapped[list[str]] = mapped_column(ARRAY(UUID), default=list)
    expected_action: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # approve | deny | partial | escalate | route
    expected_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    risk_tier: Mapped[str] = mapped_column(
        String(20), default="standard"
    )  # critical | standard | low
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    policy: Mapped["Policy"] = relationship(back_populates="scenarios")
    results: Mapped[list["ScenarioResult"]] = relationship(back_populates="scenario")
