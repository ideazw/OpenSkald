from __future__ import annotations

from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.memory.store import MemoryStore


class KnowledgeIngestionAgent:
    def __init__(self, knowledge_base: OpenVikingKnowledgeBase, memory: MemoryStore) -> None:
        self.knowledge_base = knowledge_base
        self.memory = memory

    def ingest(self) -> dict:
        articles = self.knowledge_base.recent_articles()
        for article in articles:
            self.memory.remember_article(article)
        return {
            "ok": True,
            "ingested": len(articles),
            "articles": [article.model_dump(mode="json") for article in articles],
        }
