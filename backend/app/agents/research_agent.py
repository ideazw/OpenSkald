from __future__ import annotations

from backend.app.domain.models import (
    SourceBrief,
)
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.memory.store import MemoryStore


class ResearchAgent:
    """Thin agent: gathers source material from knowledge base and memory."""

    def __init__(
        self, knowledge_base: OpenVikingKnowledgeBase, memory: MemoryStore
    ) -> None:
        self.knowledge_base = knowledge_base
        self.memory = memory

    async def research(self, objective: str) -> SourceBrief:
        """Return a curated set of source material for a given objective."""
        # Gather articles from both sources, preferably relevant to the objective.
        articles = self.memory.search_articles(objective, limit=10)
        if not articles:
            articles = self.memory.list_articles()[:10]
        if not articles:
            articles = self.knowledge_base.recent_articles()[:10]

        # Gather relevant memory records
        memory_records = self.memory.search_namespace(
            namespace="viking://project/", limit=10
        )

        # Topic continuity from prior content
        prior_content = self.memory.list_content()[:10]
        topic_notes = ""
        if prior_content:
            titles = [c.title for c in prior_content[-5:]]
            topic_notes = f"Recent content topics: {'; '.join(titles)}"

        return SourceBrief(
            objective=objective,
            articles=[a.model_dump(mode="json") for a in articles],
            memory_records=memory_records,
            topic_continuity_notes=topic_notes,
        )
