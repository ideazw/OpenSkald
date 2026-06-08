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


# ---------------------------------------------------------------------------
# Phase A: Memory & Runtime Tracking models
# ---------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """A generic namespace-addressable memory record (JSONL-backed)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    namespace: str
    kind: str  # "experience", "reflection", "metric", "note", "plan"
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentExperience(BaseModel):
    """Records of a single agent action for later reflection."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    action: str  # "generate", "review", "approve", "reject", "publish", "ingest"
    result: str  # "success", "failure", "partial"
    tool_calls: list[str] = Field(default_factory=list)
    content_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentReflection(BaseModel):
    """A structured lesson distilled from recent experiences."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    observation: str
    lesson: str
    recommendation: str
    confidence: float = 0.5
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentMetric(BaseModel):
    """Observable numeric metric (page views, engagement, ...)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    metric_name: str
    value: float
    dimensions: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Phase C - D: Agent runtime & collaboration models
# ---------------------------------------------------------------------------


class AgentMode(StrEnum):
    SINGLE = "single"
    COLLABORATIVE = "collaborative"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentSpec(BaseModel):
    """Declarative specification for an agent role."""

    name: str
    role: str
    instructions: str
    tools: list[str] = Field(default_factory=list)
    handoff_targets: list[str] = Field(default_factory=list)
    memory_namespaces: list[str] = Field(default_factory=list)


class AgentContext(BaseModel):
    """Input context for a single agent run."""

    workspace_id: str = "open-skald"
    objective: str
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    retrieved_memory: list[MemoryRecord] = Field(default_factory=list)
    run_id: str = Field(default_factory=lambda: str(uuid4()))


class AgentRun(BaseModel):
    """Captures the full lifecycle of one agent invocation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    mode: AgentMode = AgentMode.SINGLE
    status: AgentRunStatus = AgentRunStatus.PENDING
    input: str
    output: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    memory_writes: int = 0
    cost: float = 0.0
    latency_ms: int = 0
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class AgentResult(BaseModel):
    """Structured result returned from an agent or orchestrator."""

    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    memory_writes: list[MemoryRecord] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase D: Collaboration artifact types
# ---------------------------------------------------------------------------


class SourceBrief(BaseModel):
    """Output of ResearchAgent - a curated set of source material."""

    objective: str
    articles: list[dict[str, Any]] = Field(default_factory=list)
    memory_records: list[MemoryRecord] = Field(default_factory=list)
    topic_continuity_notes: str = ""


class PlatformDraft(BaseModel):
    """Output of WritingAgent - a draft ready for review."""

    platform: str
    title: str
    body: str
    content_type: ContentType
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewReport(BaseModel):
    """Output of ReviewAgent - quality assessment with veto."""

    approved: bool
    notes: str = ""
    revision_suggestions: str = ""
    platform_issues: list[str] = Field(default_factory=list)
    factual_issues: list[str] = Field(default_factory=list)
