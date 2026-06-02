from pathlib import Path

import pytest

from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.config.settings import PublisherConfig
from backend.app.domain.models import (
    ContentType,
    GeneratedContent,
    PublishResult,
    ReviewStatus,
)
from backend.app.memory.store import MemoryStore
from backend.app.publishers.base import Publisher, PublisherRegistry


class FailingPublisher(Publisher):
    async def publish(self, content: GeneratedContent) -> PublishResult:
        raise RuntimeError("upstream publish failed")


@pytest.mark.asyncio
async def test_publishing_agent_only_publishes_approved_content(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    approved = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Approved",
        body="1/ Ready\n2/ Ship it",
        status=ReviewStatus.APPROVED,
    )
    draft = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Draft",
        body="Not ready",
    )
    memory.remember_content(approved)
    memory.remember_content(draft)
    publishers = PublisherRegistry({"x": PublisherConfig(enabled=True, dry_run=True)})
    publishers.load()
    agent = PublishingAgent(memory, publishers)

    results = await agent.publish_approved(["x"])

    assert [result["content_id"] for result in results] == [approved.id]
    published = memory.get_content(approved.id)
    assert published.status == ReviewStatus.PUBLISHED
    assert published.published_at is not None
    assert published.metadata["publish_result"]["dry_run"] is True
    assert memory.get_content(draft.id).status == ReviewStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_publishing_agent_records_validation_errors_without_publishing(
    tmp_path: Path,
) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    approved = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Approved",
        body="x" * 281,
        status=ReviewStatus.APPROVED,
    )
    memory.remember_content(approved)
    publishers = PublisherRegistry({"x": PublisherConfig(enabled=True, dry_run=True)})
    publishers.load()
    agent = PublishingAgent(memory, publishers)

    results = await agent.publish_approved(["x"])

    stored = memory.get_content(approved.id)
    assert results == []
    assert stored.status == ReviewStatus.APPROVED
    assert stored.published_at is None
    assert "280 characters" in stored.metadata["publish_validation_errors"][0]


@pytest.mark.asyncio
async def test_publishing_agent_skips_disabled_publishers(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    approved = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Approved",
        body="1/ Ready",
        status=ReviewStatus.APPROVED,
    )
    memory.remember_content(approved)
    publishers = PublisherRegistry({"x": PublisherConfig(enabled=False, dry_run=True)})
    publishers.load()
    agent = PublishingAgent(memory, publishers)

    results = await agent.publish_approved(["x"])

    stored = memory.get_content(approved.id)
    assert results == []
    assert stored.status == ReviewStatus.APPROVED
    assert "disabled" in stored.metadata["publish_validation_errors"][0]


@pytest.mark.asyncio
async def test_publishing_agent_records_publish_exception_for_retry(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    approved = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Approved",
        body="1/ Ready",
        status=ReviewStatus.APPROVED,
    )
    memory.remember_content(approved)
    publishers = PublisherRegistry({})
    failing = FailingPublisher(PublisherConfig(enabled=True, dry_run=False))
    failing.platform = "x"
    publishers._publishers["x"] = failing
    agent = PublishingAgent(memory, publishers)

    result = await agent.publish_content(approved)

    stored = memory.get_content(approved.id)
    assert result is None
    assert stored.status == ReviewStatus.APPROVED
    assert stored.published_at is None
    assert stored.metadata["last_publish_error"]["type"] == "RuntimeError"
    assert "upstream publish failed" in stored.metadata["last_publish_error"]["message"]
