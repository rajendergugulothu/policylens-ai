from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Literal


class EvaluationRunCreate(BaseModel):
    policy_id: UUID
    version_label: str | None = None
    agent_type: Literal["endpoint", "batch_upload"] = "endpoint"
    agent_endpoint_url: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    created_by: str | None = None


class EvaluationRunRead(BaseModel):
    id: UUID
    workspace_id: UUID
    policy_id: UUID
    version_label: str | None
    agent_type: str
    status: str
    total_scenarios: int
    passed: int
    failed: int
    critical_violations: int
    decision_accuracy_pct: float | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScenarioResultRead(BaseModel):
    id: UUID
    evaluation_run_id: UUID
    scenario_id: UUID
    agent_response: str | None
    verdict: str
    evaluation_method: str
    failure_severity: str | None
    likely_cause: str | None
    explanation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FindingRead(BaseModel):
    id: UUID
    evaluation_run_id: UUID
    title: str
    severity: str
    likely_cause: str | None
    violated_clause: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BatchUploadItem(BaseModel):
    scenario_id: UUID
    agent_response: str


class BatchUpload(BaseModel):
    responses: list[BatchUploadItem]
