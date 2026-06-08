from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.reflection_agent import ReflectionAgent
from backend.app.domain.models import ContentType, GeneratedContent, MemoryRecord, ReviewStatus
from backend.app.llm.provider import DemoLLMProvider
from backend.app.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_reflection_from_failed_experiences(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    llm = DemoLLMProvider()

    # Add a failed experience
    memory.append_memory_record(
        MemoryRecord(
            namespace="viking://agent/experience",
            kind="experience",
            payload={
                "action": "generate",
                "result": "failure",
                "errors": ["No articles available for generation"],
            },
            source="test",
        )
    )

    agent = ReflectionAgent(memory, llm)
    reflections = await agent.discover()

    assert len(reflections) >= 1
    # Should find at least one reflection from the failed experience
    error_reflections = [r for r in reflections if "failed" in r.observation.lower()]
    assert len(error_reflections) >= 1
    assert all(r.lesson for r in reflections)
    assert all(r.recommendation for r in reflections)


@pytest.mark.asyncio
async def test_reflection_from_rejected_content(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    llm = DemoLLMProvider()

    # Add rejected content
    memory.remember_content(
        GeneratedContent(
            content_type=ContentType.DAILY_SUMMARY,
            platform="x",
            title="Rejected Post",
            body="1/ Not good enough",
            status=ReviewStatus.REJECTED,
            review_note="Too short, lacks technical depth",
        )
    )

    agent = ReflectionAgent(memory, llm)
    reflections = await agent.discover()

    assert any("rejected" in r.observation.lower() for r in reflections)


@pytest.mark.asyncio
async def test_reflection_from_successful_publish(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    llm = DemoLLMProvider()

    memory.remember_content(
        GeneratedContent(
            content_type=ContentType.DAILY_SUMMARY,
            platform="blog",
            title="Success Post",
            body="## Great Content\n\nThis is published.",
            status=ReviewStatus.PUBLISHED,
        )
    )

    agent = ReflectionAgent(memory, llm)
    reflections = await agent.discover()

    assert any("published" in r.observation.lower() for r in reflections)


@pytest.mark.asyncio
async def test_reflect_on_experiences_direct(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    llm = DemoLLMProvider()

    experiences = [
        MemoryRecord(
            namespace="viking://agent/experience",
            kind="experience",
            payload={"action": "test", "result": "failure", "errors": ["test error"]},
            source="test",
        )
    ]

    agent = ReflectionAgent(memory, llm)
    reflections = await agent.reflect_on_experiences(experiences)

    assert len(reflections) == 1
    assert "test error" in reflections[0].observation
    assert reflections[0].recommendation
    assert reflections[0].lesson
