"""
Policy ingestion service.
Accepts PDF (via pdfplumber), plain text, or Notion URL.
Produces a Policy record with raw_text and source metadata.
"""

import io
import os
import httpx
import pdfplumber
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models.policy import Policy
from models.workspace import Workspace


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")


async def _get_next_version(db: AsyncSession, workspace_id: str) -> int:
    """Auto-increment policy version within a workspace."""
    result = await db.execute(
        select(func.max(Policy.version)).where(Policy.workspace_id == workspace_id)
    )
    current_max = result.scalar()
    return (current_max or 0) + 1


async def ingest_pdf(
    db: AsyncSession,
    workspace_id: str,
    file: UploadFile,
    uploaded_by: str | None = None,
) -> Policy:
    """Extract text from a PDF upload, preserving page structure."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    text_chunks = []
    page_count = 0

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                # Prefix each page with a separator the extraction module can use
                # to rebuild source citations: [PAGE:N] ... text ...
                text_chunks.append(f"[PAGE:{i}]\n{page_text.strip()}")

    if not text_chunks:
        raise HTTPException(status_code=422, detail="No text could be extracted from the PDF. Try a text-layer PDF rather than a scanned image.")

    raw_text = "\n\n".join(text_chunks)
    version = await _get_next_version(db, workspace_id)

    policy = Policy(
        workspace_id=workspace_id,
        version=version,
        title=file.filename.removesuffix(".pdf") if file.filename else None,
        source_format="pdf",
        raw_text=raw_text,
        page_count=page_count,
        uploaded_by=uploaded_by,
    )
    db.add(policy)
    await db.flush()
    return policy


async def ingest_text(
    db: AsyncSession,
    workspace_id: str,
    raw_text: str,
    title: str | None = None,
    uploaded_by: str | None = None,
) -> Policy:
    """Store plain text directly. No page markers."""
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Policy text is empty.")

    version = await _get_next_version(db, workspace_id)

    policy = Policy(
        workspace_id=workspace_id,
        version=version,
        title=title,
        source_format="text",
        raw_text=raw_text.strip(),
        uploaded_by=uploaded_by,
    )
    db.add(policy)
    await db.flush()
    return policy


async def ingest_notion_url(
    db: AsyncSession,
    workspace_id: str,
    notion_url: str,
    uploaded_by: str | None = None,
) -> Policy:
    """
    Fetch a Notion page via the API and extract its content block-by-block.
    Each block is tagged with its block ID for source citation URL construction.
    Requires NOTION_TOKEN env var (Integration token with read access).
    """
    if not NOTION_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Notion integration is not configured. Set NOTION_TOKEN in environment."
        )

    # Extract page ID from URL
    # Notion URLs: https://notion.so/workspace/Title-<page_id>
    # or https://www.notion.so/<page_id>
    page_id = _extract_notion_page_id(notion_url)
    if not page_id:
        raise HTTPException(status_code=400, detail="Could not extract page ID from Notion URL.")

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
    }

    async with httpx.AsyncClient() as client:
        # Fetch page metadata
        page_resp = await client.get(f"{NOTION_API_BASE}/pages/{page_id}", headers=headers)
        if page_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Notion page not found. Check the URL and integration permissions.")
        if page_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Notion API error: {page_resp.status_code}")

        page_data = page_resp.json()
        title = _extract_notion_title(page_data)

        # Fetch all blocks (handles pagination)
        blocks = await _fetch_all_blocks(client, page_id, headers)

    text_chunks = []
    for block in blocks:
        block_text = _block_to_text(block)
        if block_text:
            block_url = f"{notion_url}#{block['id'].replace('-', '')}"
            # Tag each block with its anchor URL for source citations
            text_chunks.append(f"[BLOCK:{block['id']}|URL:{block_url}]\n{block_text}")

    raw_text = "\n\n".join(text_chunks)
    version = await _get_next_version(db, workspace_id)

    policy = Policy(
        workspace_id=workspace_id,
        version=version,
        title=title,
        source_format="notion_url",
        source_url=notion_url,
        raw_text=raw_text,
        uploaded_by=uploaded_by,
    )
    db.add(policy)
    await db.flush()
    return policy


async def _fetch_all_blocks(
    client: httpx.AsyncClient, page_id: str, headers: dict
) -> list[dict]:
    """Paginate through all blocks in a Notion page."""
    blocks = []
    cursor = None

    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        resp = await client.get(
            f"{NOTION_API_BASE}/blocks/{page_id}/children",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        blocks.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return blocks


def _extract_notion_page_id(url: str) -> str | None:
    """Extract UUID from Notion URL. Handles various URL formats."""
    import re
    # Match 32-char hex or UUID with dashes
    match = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-f0-9]{32})", url)
    if match:
        raw = match.group(1).replace("-", "")
        # Format as UUID
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return None


def _extract_notion_title(page_data: dict) -> str | None:
    """Pull the page title from Notion page metadata."""
    props = page_data.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            texts = prop.get("title", [])
            if texts:
                return "".join(t.get("plain_text", "") for t in texts)
    return None


def _block_to_text(block: dict) -> str:
    """Convert a Notion block to plain text. Handles the common rich text block types."""
    block_type = block.get("type", "")
    content = block.get(block_type, {})
    rich_text = content.get("rich_text", [])
    text = "".join(t.get("plain_text", "") for t in rich_text)

    if block_type == "heading_1":
        return f"# {text}"
    elif block_type == "heading_2":
        return f"## {text}"
    elif block_type == "heading_3":
        return f"### {text}"
    elif block_type == "bulleted_list_item":
        return f"• {text}"
    elif block_type == "numbered_list_item":
        return f"1. {text}"
    elif block_type in ("paragraph", "quote", "callout"):
        return text
    elif block_type == "divider":
        return "---"
    else:
        return text  # Return text for any other block types that have rich_text
