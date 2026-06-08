from __future__ import annotations

from backend.app.domain.models import ContentType, GeneratedContent, MemoryRecord, SkillProposal
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
        import time
        start = time.monotonic()
        articles = self.memory.list_articles()
        article_source = "index"
        if not articles:
            articles = self.knowledge_base.recent_articles()
            article_source = "openviking"
        if not articles:
            raise ValueError("No OpenViking articles available for generation")
        generated: list[GeneratedContent] = []
        errors: list[str] = []
        for platform in platforms:
            skills = self.skills.for_content(content_type, platform)
            for skill in skills:
                try:
                    body = await skill.run(articles, self.llm)
                except Exception as exc:
                    errors.append(f"{platform}/{skill.metadata.name}: {exc}")
                    continue
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
        duration_ms = int((time.monotonic() - start) * 1000)
        # Record experience
        result = "success"
        if errors:
            result = "failure" if len(generated) == 0 else "partial"
        self.memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/experience",
                kind="experience",
                payload={
                    "action": "generate",
                    "result": result,
                    "content_type": content_type.value,
                    "platforms": platforms,
                    "article_source": article_source,
                    "article_count": len(articles),
                    "generated_count": len(generated),
                    "duration_ms": duration_ms,
                    "errors": errors,
                },
                source="ContentAgent.generate",
            )
        )
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
