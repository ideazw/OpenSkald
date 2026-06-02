from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ContentType(StrEnum):
    DAILY_SUMMARY = "daily_summary"
    WEEKLY_SUMMARY = "weekly_summary"
    HOT_TOPIC_ANALYSIS = "hot_topic_analysis"
    DEEP_TECHNICAL_ANALYSIS = "deep_technical_analysis"


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class Article(BaseModel):
    id: str
    title: str
    content: str
    source_path: str | None = None
    url: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class GeneratedContent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    content_type: ContentType
    platform: str
    title: str
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ReviewStatus = ReviewStatus.PENDING_REVIEW
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    review_note: str | None = None
    published_at: datetime | None = None


class PublishValidationResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)


class PublishResult(BaseModel):
    platform: str
    content_id: str
    dry_run: bool = True
    external_id: str | None = None
    url: str | None = None
    title: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillProposal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    reason: str
    proposed_skill_name: str
    draft_prompt: str
    content_types: list[ContentType] = Field(default_factory=lambda: [ContentType.DAILY_SUMMARY])
    platforms: list[str] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.PENDING_REVIEW
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    review_note: str | None = None
    draft_skill_path: str | None = None
