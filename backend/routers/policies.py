from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from database import get_db
from models.policy import Policy
from models.policy_rule import PolicyRule, AmbiguityFlag
from models.workspace import Workspace
from schemas.policy import PolicyRead, PolicyUploadResponse
from services.ingestion import ingest_pdf, ingest_text, ingest_notion_url

router = APIRouter(prefix="/policies", tags=["policies"])


async def _enrich_policy(db: AsyncSession, policy: Policy) -> PolicyRead:
    """Add derived counts to a policy record."""
    rule_count = await db.scalar(
        select(func.count(PolicyRule.id)).where(PolicyRule.policy_id == policy.id)
    ) or 0
    approved_count = await db.scalar(
        select(func.count(PolicyRule.id))
        .where(PolicyRule.policy_id == policy.id, PolicyRule.status == "approved")
    ) or 0
    ambiguity_count = await db.scalar(
        select(func.count(AmbiguityFlag.id))
        .join(PolicyRule, AmbiguityFlag.rule_id == PolicyRule.id)
        .where(PolicyRule.policy_id == policy.id, AmbiguityFlag.status == "open")
    ) or 0

    item = PolicyRead.model_validate(policy)
    item.rule_count = rule_count
    item.approved_rule_count = approved_count
    item.open_ambiguity_count = ambiguity_count
    return item


# ─── PDF upload ────────────────────────────────────────────────────────────────

@router.post("/upload/pdf", response_model=PolicyUploadResponse, status_code=201)
async def upload_policy_pdf(
    workspace_id: UUID = Form(...),
    uploaded_by: str | None = Form(None),
    file: UploadFile = File(..., description="PDF policy document"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF policy document.
    Text is extracted with page-level source markers preserved.
    """
    if not file.content_type or "pdf" not in file.content_type.lower():
        # Accept even if content_type is wrong — validate by parsing
        pass

    await _assert_workspace_exists(db, workspace_id)

    policy = await ingest_pdf(db, str(workspace_id), file, uploaded_by)
    enriched = await _enrich_policy(db, policy)
    preview = (policy.raw_text or "")[:500]

    return PolicyUploadResponse(
        policy=enriched,
        extracted_text_preview=preview,
        pages_extracted=policy.page_count,
        message=f"PDF ingested. {policy.page_count} page(s) extracted. Proceed to rule extraction.",
    )


# ─── Plain text paste ──────────────────────────────────────────────────────────

@router.post("/upload/text", response_model=PolicyUploadResponse, status_code=201)
async def upload_policy_text(
    workspace_id: UUID = Form(...),
    raw_text: str = Form(..., min_length=50),
    title: str | None = Form(None),
    uploaded_by: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Paste policy text directly.
    Use this when the policy lives in a wiki, email, or other text source.
    """
    await _assert_workspace_exists(db, workspace_id)

    policy = await ingest_text(db, str(workspace_id), raw_text, title, uploaded_by)
    enriched = await _enrich_policy(db, policy)
    preview = raw_text[:500]

    return PolicyUploadResponse(
        policy=enriched,
        extracted_text_preview=preview,
        pages_extracted=None,
        message="Text policy ingested. Proceed to rule extraction.",
    )


# ─── Notion URL ───────────────────────────────────────────────────────────────

@router.post("/upload/notion", response_model=PolicyUploadResponse, status_code=201)
async def upload_policy_notion(
    workspace_id: UUID = Form(...),
    notion_url: str = Form(..., description="Public or shared Notion page URL"),
    uploaded_by: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a Notion page by URL.
    Requires NOTION_TOKEN env var. Each block is tagged with its anchor URL
    so rule source citations link directly to the Notion page section.
    """
    await _assert_workspace_exists(db, workspace_id)

    policy = await ingest_notion_url(db, str(workspace_id), notion_url, uploaded_by)
    enriched = await _enrich_policy(db, policy)
    preview = (policy.raw_text or "")[:500]

    return PolicyUploadResponse(
        policy=enriched,
        extracted_text_preview=preview,
        pages_extracted=None,
        message="Notion page ingested. Proceed to rule extraction.",
    )


# ─── List / get ───────────────────────────────────────────────────────────────

@router.get("/workspace/{workspace_id}", response_model=list[PolicyRead])
async def list_policies(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all policies for a workspace, newest first."""
    await _assert_workspace_exists(db, workspace_id)

    result = await db.execute(
        select(Policy)
        .where(Policy.workspace_id == workspace_id)
        .order_by(Policy.version.desc())
    )
    policies = result.scalars().all()
    return [await _enrich_policy(db, p) for p in policies]


@router.get("/{policy_id}", response_model=PolicyRead)
async def get_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single policy by ID."""
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    return await _enrich_policy(db, policy)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _assert_workspace_exists(db: AsyncSession, workspace_id: UUID) -> None:
    result = await db.execute(
        select(Workspace.id).where(Workspace.id == workspace_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workspace not found.")
