from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.content_agent import ContentAgent
from backend.app.agents.growth_agent import GrowthAgent
from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.agents.reflection_agent import ReflectionAgent
from backend.app.agents.runtime import OpenSkaldAgentRuntime
from backend.app.agents.skill_evolution_agent import SkillEvolutionAgent
from backend.app.config.settings import OpenVikingConfig
from backend.app.domain.models import AgentMode, Article, ContentType
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.llm.provider import DemoLLMProvider
from backend.app.memory.store import MemoryStore
from backend.app.publishers.base import PublisherRegistry
from backend.app.skills.base import SkillRegistry


@pytest.mark.asyncio
async def test_runtime_single_mode(tmp_path: Path) -> None:
    memory = MemoryStore(
        tmp_path / "memory.jsonl",
        tmp_path / "skill_proposals.jsonl",
        tmp_path / "articles.jsonl",
    )
    memory.remember_article(
        Article(
            id="test-art",
            title="Test Article",
            content="This is a test article for content generation.",
        )
    )
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()

    # Build knowledge base with test articles
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "test.md").write_text(
        "---\ntitle: Test\ntags: [test]\n---\nTest content.",
        encoding="utf-8",
    )

    llm = DemoLLMProvider()
    content_agent = ContentAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        skills,
        llm,
        memory,
    )
    publishers = PublisherRegistry({})
    publishers.load()
    publishing_agent = PublishingAgent(memory, publishers)
    reflection_agent = ReflectionAgent(memory, llm)
    growth_agent = GrowthAgent(memory)
    skill_evolution_agent = SkillEvolutionAgent(memory, tmp_path / "skills")

    runtime = OpenSkaldAgentRuntime(
        content_agent=content_agent,
        publishing_agent=publishing_agent,
        reflection_agent=reflection_agent,
        growth_agent=growth_agent,
        skill_evolution_agent=skill_evolution_agent,
        memory=memory,
    )

    run = await runtime.run(
        objective="Generate a test post",
        content_type=ContentType.DAILY_SUMMARY,
        platforms=["blog"],
        mode=AgentMode.SINGLE,
    )

    assert run.status.value in ("completed", "partial")
    assert len(run.artifacts) >= 1
    assert run.latency_ms >= 0
    assert run.memory_writes >= 0


@pytest.mark.asyncio
async def test_runtime_get_and_list_runs(tmp_path: Path) -> None:
    memory = MemoryStore(
        tmp_path / "memory.jsonl",
        tmp_path / "skill_proposals.jsonl",
        tmp_path / "articles.jsonl",
    )
    memory.remember_article(
        Article(id="art-1", title="Article 1", content="Content for runtime test.")
    )
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "a.md").write_text("---\ntitle: A\n---\nContent.", encoding="utf-8")

    llm = DemoLLMProvider()
    runtime = OpenSkaldAgentRuntime(
        content_agent=ContentAgent(
            OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
            skills, llm, memory,
        ),
        publishing_agent=PublishingAgent(memory, PublisherRegistry({})),
        reflection_agent=ReflectionAgent(memory, llm),
        growth_agent=GrowthAgent(memory),
        skill_evolution_agent=SkillEvolutionAgent(memory, tmp_path / "skills"),
        memory=memory,
    )

    run = await runtime.run(
        objective="List test",
        content_type=ContentType.DAILY_SUMMARY,
        platforms=["blog"],
        mode=AgentMode.SINGLE,
    )

    fetched = runtime.get_run(run.id)
    assert fetched is not None
    assert fetched["id"] == run.id

    runs = runtime.list_runs()
    assert len(runs) >= 1


@pytest.mark.asyncio
async def test_runtime_reads_latest_append_only_run_state(tmp_path: Path) -> None:
    memory = MemoryStore(
        tmp_path / "memory.jsonl",
        tmp_path / "skill_proposals.jsonl",
        tmp_path / "articles.jsonl",
    )
    memory.remember_article(
        Article(id="art-1", title="Article 1", content="Content for runtime test.")
    )
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "a.md").write_text("---\ntitle: A\n---\nContent.", encoding="utf-8")

    llm = DemoLLMProvider()
    runtime = OpenSkaldAgentRuntime(
        content_agent=ContentAgent(
            OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
            skills,
            llm,
            memory,
        ),
        publishing_agent=PublishingAgent(memory, PublisherRegistry({})),
        reflection_agent=ReflectionAgent(memory, llm),
        growth_agent=GrowthAgent(memory),
        skill_evolution_agent=SkillEvolutionAgent(memory, tmp_path / "skills"),
        memory=memory,
    )

    run = await runtime.run(
        objective="Append-only state test",
        content_type=ContentType.DAILY_SUMMARY,
        platforms=["blog"],
        mode=AgentMode.SINGLE,
    )

    run.output = "latest state"
    run.latency_ms += 1000
    runtime._update_agent_run(run)

    fetched = runtime.get_run(run.id)
    assert fetched is not None
    assert fetched["output"] == "latest state"

    matching = [item for item in runtime.list_runs(limit=10) if item["id"] == run.id]
    assert len(matching) == 1
    assert matching[0]["output"] == "latest state"
