from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.research_agent import ResearchAgent
from backend.app.config.settings import OpenVikingConfig
from backend.app.domain.models import Article
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_research_agent_returns_source_brief(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "article.md").write_text(
        "---\ntitle: Test Article\ntags: [test]\n---\nTest body.",
        encoding="utf-8",
    )

    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = ResearchAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        memory,
    )

    brief = await agent.research("Test RAG topic")

    assert brief.objective == "Test RAG topic"
    assert len(brief.articles) >= 1
    assert brief.articles[0]["title"] == "Test Article"


@pytest.mark.asyncio
async def test_research_agent_returns_empty_brief_when_no_knowledge(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "empty_knowledge"
    knowledge_path.mkdir()

    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = ResearchAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        memory,
    )

    brief = await agent.research("No content")
    assert len(brief.articles) == 0


@pytest.mark.asyncio
async def test_research_agent_prefers_relevant_limited_memory_articles(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()

    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    for i in range(12):
        memory.remember_article(
            Article(
                id=f"rag-{i}",
                title=f"RAG Article {i}",
                content="Retrieval augmented generation notes.",
            )
        )
    memory.remember_article(
        Article(id="other", title="Other", content="Unrelated content.")
    )
    agent = ResearchAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
        memory,
    )

    brief = await agent.research("RAG")

    assert len(brief.articles) == 10
    assert all("RAG" in article["title"] for article in brief.articles)
