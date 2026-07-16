from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from uuid import UUID

from database import get_db
from models.release import Release, ReleaseSignature
from models.evaluation import Finding
from schemas.evaluation import FindingRead
from services.report import build_release, sign_release, build_version_comparison

router = APIRouter(prefix="/releases", tags=["releases"])


class ReleaseCreate(BaseModel):
    evaluation_run_id: UUID
    created_by: str | None = None


class ReleaseRead(BaseModel):
    id: UUID
    workspace_id: UUID
    evaluation_run_id: UUID
    recommendation: str
    recommendation_reason: str
    critical_violation_rate: float | None
    decision_accuracy_pct: float | None
    scenario_coverage_pct: float | None
    open_findings: int
    status: str
    signatures: list[dict] = []

    model_config = {"from_attributes": True}


class SignatureRequest(BaseModel):
    signer_name: str = Field(..., example="Sarah Chen")
    signer_role: str = Field(..., example="vp_operations")
    notes: str | None = None


class VersionCompareRequest(BaseModel):
    baseline_run_id: UUID
    comparison_run_id: UUID
    workspace_id: UUID


@router.post("/", response_model=ReleaseRead, status_code=201)
async def create_release(
    payload: ReleaseCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Build a launch-readiness report from a completed evaluation run.
    Computes recommendation: ready / conditionally_ready / not_ready.
    """
    try:
        release = await build_release(db, str(payload.evaluation_run_id), payload.created_by or "system")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return await _enrich_release(db, release)


@router.post("/{release_id}/sign", response_model=ReleaseRead)
async def sign(
    release_id: UUID,
    payload: SignatureRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Add a signature to a release.
    After 2 signatures the release moves to 'approved'.
    Dual sign-off requirement: QA lead + VP Operations (or Compliance).
    """
    try:
        release = await sign_release(
            db, str(release_id), payload.signer_name, payload.signer_role, payload.notes
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return await _enrich_release(db, release)


@router.get("/{release_id}", response_model=ReleaseRead)
async def get_release(release_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Release).where(Release.id == release_id))
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found.")
    return await _enrich_release(db, release)


@router.get("/{release_id}/findings", response_model=list[FindingRead])
async def get_release_findings(release_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Release).where(Release.id == release_id))
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found.")

    findings_result = await db.execute(
        select(Finding)
        .where(Finding.evaluation_run_id == release.evaluation_run_id)
        .order_by(Finding.severity, Finding.created_at)
    )
    return findings_result.scalars().all()


@router.post("/compare", response_model=dict)
async def compare_versions(
    payload: VersionCompareRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Compare two evaluation runs (FR-8).
    Returns accuracy delta, new failures, resolved failures, regression flag.
    """
    try:
        return await build_version_comparison(
            db,
            str(payload.baseline_run_id),
            str(payload.comparison_run_id),
            str(payload.workspace_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


async def _enrich_release(db: AsyncSession, release: Release) -> ReleaseRead:
    sigs_result = await db.execute(
        select(ReleaseSignature).where(ReleaseSignature.release_id == release.id)
    )
    sigs = [
        {
            "signer_name": s.signer_name,
            "signer_role": s.signer_role,
            "signed_at": s.signed_at.isoformat(),
        }
        for s in sigs_result.scalars().all()
    ]
    item = ReleaseRead.model_validate(release)
    item.signatures = sigs
    return item
