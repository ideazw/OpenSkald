from __future__ import annotations

from backend.app.domain.models import ContentType, GeneratedContent, SkillProposal
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.llm.provider import LLMProvider
from backend.app.memory.store import MemoryStore
from backend.app.skills.base import SkillRegistry


class ContentAgent:
    def __init__(
        self,
        knowledge_base: OpenVikingKnowledgeBase,
        skills: SkillRegistry,
        llm: LLMProvider,
        memory: MemoryStore,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.skills = skills
        self.llm = llm
        self.memory = memory

    async def generate(
        self,
        content_type: ContentType,
        platforms: list[str],
    ) -> list[GeneratedContent]:
        articles = self.memory.list_articles()
        article_source = "index"
        if not articles:
            articles = self.knowledge_base.recent_articles()
            article_source = "openviking"
        if not articles:
            raise ValueError("No OpenViking articles available for generation")
        generated: list[GeneratedContent] = []
        for platform in platforms:
            skills = self.skills.for_content(content_type, platform)
            for skill in skills:
                body = await skill.run(articles, self.llm)
                item = GeneratedContent(
                    content_type=content_type,
                    platform=platform,
                    title=f"{content_type.value.replace('_', ' ').title()} for {platform}",
                    body=body,
                    metadata={
                        "skill": skill.metadata.name,
                        "article_count": len(articles),
                        "article_source": article_source,
                    },
                )
                self.memory.remember_content(item)
                generated.append(item)
        return generated

    def propose_skill(
        self,
        title: str,
        reason: str,
        skill_name: str,
        draft_prompt: str,
    ) -> SkillProposal:
        proposal = SkillProposal(
            title=title,
            reason=reason,
            proposed_skill_name=skill_name,
            draft_prompt=draft_prompt,
        )
        self.memory.store_skill_proposal(proposal)
        return proposal
