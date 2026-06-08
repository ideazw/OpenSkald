from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.growth_agent import GrowthAgent
from backend.app.agents.orchestrator import MultiAgentOrchestrator
from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.agents.reflection_agent import ReflectionAgent
from backend.app.agents.research_agent import ResearchAgent
from backend.app.agents.review_agent import ReviewAgent
from backend.app.agents.writing_agent import WritingAgent
from backend.app.config.settings import OpenVikingConfig
from backend.app.domain.models import ContentType, PlatformDraft, ReviewReport
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.llm.provider import DemoLLMProvider
from backend.app.memory.store import MemoryStore
from backend.app.publishers.base import PublisherRegistry
from backend.app.skills.base import SkillRegistry


@pytest.mark.asyncio
async def test_orchestrator_full_workflow(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    llm = DemoLLMProvider()

    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "test.md").write_text(
        "---\ntitle: RAG Systems\ntags: [rag]\n---\nRAG systems improve LLM outputs.\n",
        encoding="utf-8",
    )

    research_agent = ResearchAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        memory,
    )
    writing_agent = WritingAgent(skills, llm)

    class AcceptingReviewAgent(ReviewAgent):
        """Always approves for deterministic testing."""

        async def review(self, draft: PlatformDraft) -> ReviewReport:
            return ReviewReport(approved=True, notes="Auto-approved in test")

    review_agent = AcceptingReviewAgent(memory)
    publishers = PublisherRegistry({})
    publishers.load()
    publishing_agent = PublishingAgent(memory, publishers)
    reflection_agent = ReflectionAgent(memory, llm)
    growth_agent = GrowthAgent(memory)

    orchestrator = MultiAgentOrchestrator(
        research_agent=research_agent,
        writing_agent=writing_agent,
        review_agent=review_agent,
        publishing_agent=publishing_agent,
        reflection_agent=reflection_agent,
        growth_agent=growth_agent,
        memory=memory,
    )

    result = await orchestrator.run(
        objective="Test orchestration",
        content_type=ContentType.DAILY_SUMMARY,
        platforms=["blog"],
        max_turns=8,
        require_review=True,
    )

    # research + writing + review + store (reflection/growth add memory_writes)
    assert len(result.artifacts) >= 4
    assert result.errors == [] or all("failed" not in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_orchestrator_with_review_failure(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    llm = DemoLLMProvider()

    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "t.md").write_text("---\ntitle: T\n---\nContent.\n", encoding="utf-8")

    class RejectingReviewAgent(ReviewAgent):
        async def review(self, draft: PlatformDraft) -> ReviewReport:
            return ReviewReport(
                approved=False,
                notes="Rejected in test",
                platform_issues=["280 character limit"],
                revision_suggestions="Shorten content",
            )

    orchestrator = MultiAgentOrchestrator(
        research_agent=ResearchAgent(
            OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
            memory,
        ),
        writing_agent=WritingAgent(skills, llm),
        review_agent=RejectingReviewAgent(memory),
        publishing_agent=PublishingAgent(memory, PublisherRegistry({})),
        reflection_agent=ReflectionAgent(memory, llm),
        growth_agent=GrowthAgent(memory),
        memory=memory,
    )

    result = await orchestrator.run(
        objective="Test review failure",
        content_type=ContentType.DAILY_SUMMARY,
        platforms=["x"],
        max_turns=8,
        require_review=True,
    )

    # Review should fail and generate errors, but workflow continues
    assert len(result.errors) > 0
    assert any("Review failed" in e for e in result.errors)


@pytest.mark.asyncio
async def test_orchestrator_review_exception_keeps_reports_aligned(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    llm = DemoLLMProvider()

    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "t.md").write_text("---\ntitle: T\n---\nContent.\n", encoding="utf-8")

    class RaisingReviewAgent(ReviewAgent):
        async def review(self, draft: PlatformDraft) -> ReviewReport:
            raise RuntimeError(f"cannot review {draft.platform}")

    orchestrator = MultiAgentOrchestrator(
        research_agent=ResearchAgent(
            OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
            memory,
        ),
        writing_agent=WritingAgent(skills, llm),
        review_agent=RaisingReviewAgent(memory),
        publishing_agent=PublishingAgent(memory, PublisherRegistry({})),
        reflection_agent=ReflectionAgent(memory, llm),
        growth_agent=GrowthAgent(memory),
        memory=memory,
    )

    result = await orchestrator.run(
        objective="Test review exception",
        content_type=ContentType.DAILY_SUMMARY,
        platforms=["blog"],
        max_turns=8,
        require_review=True,
    )

    assert any("ReviewAgent failed for blog" in error for error in result.errors)
    assert any(artifact["type"] == "stored_content" for artifact in result.artifacts)


@pytest.mark.asyncio
async def test_orchestrator_x_revision_truncates_without_emptying_body(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    llm = DemoLLMProvider()

    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "t.md").write_text("---\ntitle: T\n---\nContent.\n", encoding="utf-8")

    class LongWritingAgent(WritingAgent):
        async def write(
            self, brief, content_type: ContentType, platforms: list[str]
        ) -> list[PlatformDraft]:
            return [
                PlatformDraft(
                    platform="x",
                    title="Long X",
                    body="x" * 400,
                    content_type=content_type,
                )
            ]

    class RejectingReviewAgent(ReviewAgent):
        async def review(self, draft: PlatformDraft) -> ReviewReport:
            return ReviewReport(
                approved=False,
                platform_issues=["X posts exceed 280 character limit"],
                revision_suggestions="Shorten content",
            )

    orchestrator = MultiAgentOrchestrator(
        research_agent=ResearchAgent(
            OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
            memory,
        ),
        writing_agent=LongWritingAgent(skills, llm),
        review_agent=RejectingReviewAgent(memory),
        publishing_agent=PublishingAgent(memory, PublisherRegistry({})),
        reflection_agent=ReflectionAgent(memory, llm),
        growth_agent=GrowthAgent(memory),
        memory=memory,
    )

    result = await orchestrator.run(
        objective="Test X revision",
        content_type=ContentType.DAILY_SUMMARY,
        platforms=["x"],
        max_turns=8,
        require_review=True,
    )

    revised = [artifact for artifact in result.artifacts if artifact["type"] == "revised_draft"]
    assert revised
    body = revised[0]["data"]["body"]
    assert body
    assert len(body) == 260
