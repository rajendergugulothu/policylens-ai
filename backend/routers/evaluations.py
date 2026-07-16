from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from uuid import UUID

from database import get_db
from models.evaluation import EvaluationRun, ScenarioResult, Finding
from models.workspace import Workspace
from models.policy import Policy
from schemas.evaluation import (
    EvaluationRunCreate, EvaluationRunRead,
    ScenarioResultRead, FindingRead,
    BatchUpload,
)
from services.evaluator import run_evaluation

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/", response_model=EvaluationRunRead, status_code=201)
async def create_evaluation_run(
    payload: EvaluationRunCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Create an evaluation run and start it asynchronously.
    For endpoint mode: the API calls your agent endpoint for each scenario.
    For batch_upload mode: POST /evaluations/{id}/upload-batch with responses.
    """
    pol_result = await db.execute(select(Policy).where(Policy.id == payload.policy_id))
    policy = pol_result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")

    if payload.agent_type == "endpoint" and not payload.agent_endpoint_url:
        raise HTTPException(status_code=400, detail="agent_endpoint_url is required for endpoint mode.")

    run = EvaluationRun(
        workspace_id=policy.workspace_id,
        policy_id=payload.policy_id,
        version_label=payload.version_label,
        agent_type=payload.agent_type,
        agent_endpoint_url=payload.agent_endpoint_url,
        model_name=payload.model_name,
        prompt_version=payload.prompt_version,
        created_by=payload.created_by,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    if payload.agent_type == "endpoint":
        # Run asynchronously in background
        background_tasks.add_task(_run_background, str(run.id))

    return run


async def _run_background(run_id: str):
    """Background task to execute the evaluation run."""
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            await run_evaluation(db, run_id)
            await db.commit()
        except Exception as e:
            from sqlalchemy import update
            await db.execute(
                update(EvaluationRun)
                .where(EvaluationRun.id == run_id)
                .values(status="failed")
            )
            await db.commit()
            print(f"Evaluation run {run_id} failed: {e}")


@router.post("/{run_id}/upload-batch", response_model=EvaluationRunRead)
async def upload_batch_responses(
    run_id: UUID,
    payload: BatchUpload,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload pre-recorded agent responses for batch evaluation.
    Use this when testing against saved agent outputs (e.g. from a staging environment).
    """
    run_result = await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    if run.agent_type != "batch_upload":
        raise HTTPException(status_code=400, detail="This run uses endpoint mode, not batch upload.")
    if run.status not in ("pending",):
        raise HTTPException(status_code=409, detail=f"Run is already {run.status}.")

    batch = {str(item.scenario_id): item.agent_response for item in payload.responses}
    await run_evaluation(db, str(run_id), batch_responses=batch)
    return run


@router.get("/workspace/{workspace_id}", response_model=list[EvaluationRunRead])
async def list_runs(workspace_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EvaluationRun)
        .where(EvaluationRun.workspace_id == workspace_id)
        .order_by(EvaluationRun.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{run_id}", response_model=EvaluationRunRead)
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return run


@router.get("/{run_id}/results", response_model=list[ScenarioResultRead])
async def get_results(
    run_id: UUID,
    verdict: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ScenarioResult).where(ScenarioResult.evaluation_run_id == run_id)
    if verdict:
        query = query.where(ScenarioResult.verdict == verdict)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{run_id}/findings", response_model=list[FindingRead])
async def get_findings(
    run_id: UUID,
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Finding).where(
        Finding.evaluation_run_id == run_id,
        Finding.status != "dismissed",
    )
    if severity:
        query = query.where(Finding.severity == severity)
    query = query.order_by(Finding.severity, Finding.created_at)
    result = await db.execute(query)
    return result.scalars().all()
