from pathlib import Path

from backend.app.agents.knowledge_ingestion_agent import KnowledgeIngestionAgent
from backend.app.config.settings import OpenVikingConfig
from backend.app.domain.models import Article, ContentType, ReviewStatus, SkillProposal
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.memory.store import MemoryStore


def test_knowledge_ingestion_indexes_articles_without_duplicates(tmp_path: Path) -> None:
    article = tmp_path / "knowledge" / "agent-memory.md"
    article.parent.mkdir()
    article.write_text(
        """---
title: Agent Memory
tags:
  - agents
---
# Agent Memory

Memory makes publishing workflows reusable.
""",
        encoding="utf-8",
    )
    memory = MemoryStore(
        tmp_path / "memory.jsonl",
        tmp_path / "skill_proposals.jsonl",
        tmp_path / "articles.jsonl",
    )
    agent = KnowledgeIngestionAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=article.parent)),
        memory,
    )

    first = agent.ingest()
    second = agent.ingest()
    matches = memory.search_articles("reusable")

    assert first["ingested"] == 1
    assert second["ingested"] == 1
    assert len(memory.list_articles()) == 1
    assert matches[0].title == "Agent Memory"


def test_memory_operational_summary_counts_articles_and_skill_proposals(
    tmp_path: Path,
) -> None:
    memory = MemoryStore(
        tmp_path / "memory.jsonl",
        tmp_path / "skill_proposals.jsonl",
        tmp_path / "articles.jsonl",
    )
    memory.remember_article(
        Article(
            id="article-1",
            title="Memory Article",
            content="Useful operational context.",
        )
    )
    proposal = SkillProposal(
        title="New writer",
        reason="Repeated review notes",
        proposed_skill_name="review_writer",
        draft_prompt="Write a review note.",
        content_types=[ContentType.DAILY_SUMMARY],
        status=ReviewStatus.APPROVED,
    )
    memory.store_skill_proposal(proposal)

    summary = memory.operational_summary()

    assert summary["articles"]["total"] == 1
    assert summary["skill_proposals"]["total"] == 1
    assert summary["skill_proposals"]["by_status"]["approved"] == 1
