from pathlib import Path

from backend.app.config.settings import OpenVikingConfig
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase


def test_openviking_reads_markdown_articles(tmp_path: Path) -> None:
    article = tmp_path / "agent-design.md"
    article.write_text(
        """---
title: Agent Design
tags:
  - agents
---
# Body

Clean architecture matters.
""",
        encoding="utf-8",
    )

    kb = OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=tmp_path))
    articles = kb.recent_articles()

    assert len(articles) == 1
    assert articles[0].title == "Agent Design"
    assert articles[0].tags == ["agents"]
