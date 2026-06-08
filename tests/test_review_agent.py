from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.review_agent import ReviewAgent
from backend.app.domain.models import ContentType, GeneratedContent, PlatformDraft
from backend.app.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_review_agent_approves_good_content(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = ReviewAgent(memory)

    draft = PlatformDraft(
        platform="blog",
        title="Good Content",
        body="This is a well-written blog post with sufficient length and quality.",
        content_type=ContentType.DAILY_SUMMARY,
    )

    report = await agent.review(draft)
    assert report.approved is True


@pytest.mark.asyncio
async def test_review_agent_rejects_x_overflow(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = ReviewAgent(memory)

    draft = PlatformDraft(
        platform="x",
        title="Too Long",
        body="x" * 281,
        content_type=ContentType.DAILY_SUMMARY,
    )

    report = await agent.review(draft)
    assert report.approved is False
    assert "280 character" in str(report.platform_issues)


@pytest.mark.asyncio
async def test_review_agent_reviews_stored_content(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = ReviewAgent(memory)

    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="blog",
        title="Test Content",
        body="This is test content for review. It is long enough now."
    )

    report = await agent.review_content(content)
    assert report.approved is True


@pytest.mark.asyncio
async def test_review_agent_detects_empty_title(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = ReviewAgent(memory)

    draft = PlatformDraft(
        platform="blog",
        title="",
        body="Some body content here.",
        content_type=ContentType.DAILY_SUMMARY,
    )

    report = await agent.review(draft)
    assert report.approved is False
    assert "Title is empty" in str(report.factual_issues)
