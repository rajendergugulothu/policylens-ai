from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Literal


WorkflowType = Literal["refund", "support", "cancellation", "onboarding"]


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, example="ShopFast Returns Agent v3")
    workflow_type: WorkflowType = "refund"
    created_by: str | None = None

    model_config = {"json_schema_extra": {"example": {
        "name": "ShopFast Returns Agent v3",
        "workflow_type": "refund",
        "created_by": "raj@shopfast.com"
    }}}


class WorkspaceRead(BaseModel):
    id: UUID
    name: str
    workflow_type: str
    is_sandbox: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime | None
    policy_count: int = 0

    model_config = {"from_attributes": True}
