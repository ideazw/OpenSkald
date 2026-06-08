from __future__ import annotations

from backend.app.domain.models import (
    ContentType,
    PlatformDraft,
    SourceBrief,
)
from backend.app.llm.provider import LLMProvider
from backend.app.skills.base import SkillRegistry


class WritingAgent:
    """Thin agent: generates platform drafts using existing skills."""

    def __init__(self, skills: SkillRegistry, llm: LLMProvider) -> None:
        self.skills = skills
        self.llm = llm

    async def write(
        self, brief: SourceBrief, content_type: ContentType, platforms: list[str]
    ) -> list[PlatformDraft]:
        """Generate drafts for each platform based on the source brief."""
        from backend.app.domain.models import Article

        drafts: list[PlatformDraft] = []
        articles_data = brief.articles
        articles = [Article.model_validate(a) for a in articles_data]

        for platform in platforms:
            skills = self.skills.for_content(content_type, platform)
            for skill in skills:
                # Use pre-validated Article objects.
                try:
                    body = await skill.run(articles, self.llm)
                except Exception as exc:
                    body = f"[Generation failed: {exc}]"

                drafts.append(
                    PlatformDraft(
                        platform=platform,
                        title=f"{content_type.value.replace('_', ' ').title()} for {platform}",
                        body=body,
                        content_type=content_type,
                        metadata={
                            "skill": skill.metadata.name,
                            "article_count": len(articles),
                        },
                    )
                )
        return drafts
