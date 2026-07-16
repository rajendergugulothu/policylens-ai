from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from database import get_db
from models.workspace import Workspace
from models.policy import Policy
from schemas.workspace import WorkspaceCreate, WorkspaceRead

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("/", response_model=WorkspaceRead, status_code=201)
async def create_workspace(
    payload: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new PolicyLens workspace.
    All workspaces are created in sandbox mode by default.
    """
    workspace = Workspace(
        name=payload.name,
        workflow_type=payload.workflow_type,
        created_by=payload.created_by,
        is_sandbox=True,  # Phase 1: all workspaces are sandbox
    )
    db.add(workspace)
    await db.flush()

    result = WorkspaceRead.model_validate(workspace)
    result.policy_count = 0
    return result


@router.get("/", response_model=list[WorkspaceRead])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """List all workspaces with their policy counts."""
    result = await db.execute(
        select(Workspace).order_by(Workspace.created_at.desc()).limit(limit).offset(offset)
    )
    workspaces = result.scalars().all()

    # Fetch policy counts in a single query
    if workspaces:
        ws_ids = [w.id for w in workspaces]
        count_result = await db.execute(
            select(Policy.workspace_id, func.count(Policy.id).label("cnt"))
            .where(Policy.workspace_id.in_(ws_ids))
            .group_by(Policy.workspace_id)
        )
        counts = {row.workspace_id: row.cnt for row in count_result}
    else:
        counts = {}

    output = []
    for ws in workspaces:
        item = WorkspaceRead.model_validate(ws)
        item.policy_count = counts.get(ws.id, 0)
        output.append(item)
    return output


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single workspace by ID."""
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    count_result = await db.execute(
        select(func.count(Policy.id)).where(Policy.workspace_id == workspace_id)
    )
    policy_count = count_result.scalar() or 0

    item = WorkspaceRead.model_validate(workspace)
    item.policy_count = policy_count
    return item
