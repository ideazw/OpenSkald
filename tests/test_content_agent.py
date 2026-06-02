from pathlib import Path

import pytest

from backend.app.agents.content_agent import ContentAgent
from backend.app.config.settings import MemoryConfig, OpenVikingConfig
from backend.app.domain.models import Article, ContentType
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.llm.provider import LLMProvider
from backend.app.memory.store import MemoryStore
from backend.app.skills.base import SkillRegistry


class FakeLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return f"generated from {len(system_prompt)} chars: {user_prompt[:30]}"


@pytest.mark.asyncio
async def test_agent_generates_platform_content_and_stores_memory(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "rag.md").write_text(
        "---\ntitle: RAG Notes\n---\nRetrieval quality depends on chunking.",
        encoding="utf-8",
    )
    memory_config = MemoryConfig(
        storage_path=tmp_path / "memory.jsonl",
        skill_proposals_path=tmp_path / "skill_proposals.jsonl",
    )
    memory = MemoryStore(memory_config.storage_path, memory_config.skill_proposals_path)
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    llm = FakeLLMProvider()
    agent = ContentAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        skills,
        llm,
        memory,
    )

    generated = await agent.generate(ContentType.DAILY_SUMMARY, ["x"])

    assert len(generated) == 1
    assert generated[0].platform == "x"
    assert generated[0].metadata["skill"] == "x_writer"
    assert generated[0].metadata["article_source"] == "openviking"
    assert memory.get_content(generated[0].id) is not None


@pytest.mark.asyncio
async def test_agent_prefers_ingested_article_index(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "old.md").write_text(
        "---\ntitle: Old Notes\n---\nThis should only be fallback content.",
        encoding="utf-8",
    )
    memory = MemoryStore(
        tmp_path / "memory.jsonl",
        tmp_path / "skill_proposals.jsonl",
        tmp_path / "articles.jsonl",
    )
    memory.remember_article(
        Article(
            id="indexed",
            title="Indexed Notes",
            content="Indexed memory should drive generation.",
            tags=["memory"],
        )
    )
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    llm = FakeLLMProvider()
    agent = ContentAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        skills,
        llm,
        memory,
    )

    generated = await agent.generate(ContentType.DAILY_SUMMARY, ["x"])

    assert generated[0].metadata["article_source"] == "index"
    assert "Indexed Notes" in llm.prompts[0]
    assert "Old Notes" not in llm.prompts[0]


@pytest.mark.asyncio
async def test_agent_refuses_generation_without_articles(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    memory = MemoryStore(
        tmp_path / "memory.jsonl",
        tmp_path / "skill_proposals.jsonl",
        tmp_path / "articles.jsonl",
    )
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    agent = ContentAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        skills,
        FakeLLMProvider(),
        memory,
    )

    with pytest.raises(ValueError, match="No OpenViking articles"):
        await agent.generate(ContentType.DAILY_SUMMARY, ["x"])
