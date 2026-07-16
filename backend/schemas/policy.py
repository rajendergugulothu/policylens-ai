from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from uuid import UUID
from typing import Literal


SourceFormat = Literal["pdf", "text", "notion_url"]


class PolicyCreate(BaseModel):
    """Used for text paste and Notion URL ingestion (not file upload)."""
    workspace_id: UUID
    title: str | None = None
    source_format: SourceFormat
    source_url: str | None = None  # Notion URL if source_format == "notion_url"
    raw_text: str | None = None    # Plain text if source_format == "text"
    uploaded_by: str | None = None


class PolicyRead(BaseModel):
    id: UUID
    workspace_id: UUID
    version: int
    title: str | None
    source_format: str
    source_url: str | None
    page_count: int | None
    is_active: bool
    uploaded_by: str | None
    created_at: datetime

    # Derived counts
    rule_count: int = 0
    approved_rule_count: int = 0
    open_ambiguity_count: int = 0

    model_config = {"from_attributes": True}


class PolicyUploadResponse(BaseModel):
    """Response after ingesting a policy — text extracted, ready for extraction step."""
    policy: PolicyRead
    extracted_text_preview: str  # First 500 chars of extracted text
    pages_extracted: int | None
    message: str
