from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import yaml
from pydantic import BaseModel

from backend.app.domain.models import Article, ContentType
from backend.app.llm.provider import LLMProvider


class SkillMetadata(BaseModel):
    name: str
    version: str = "0.1.0"
    enabled: bool = True
    description: str
    content_types: list[ContentType]
    platforms: list[str] = []
    system_prompt: str
    user_prompt_template: str


class Skill(ABC):
    metadata: SkillMetadata

    @abstractmethod
    async def run(self, articles: list[Article], llm: LLMProvider) -> str:
        """Execute the skill."""


class PromptSkill(Skill):
    def __init__(self, metadata: SkillMetadata) -> None:
        self.metadata = metadata

    async def run(self, articles: list[Article], llm: LLMProvider) -> str:
        article_block = "\n\n".join(
            f"# {article.title}\nTags: {', '.join(article.tags)}\n{article.content[:6000]}"
            for article in articles
        )
        prompt = self.metadata.user_prompt_template.format(articles=article_block)
        return await llm.generate(self.metadata.system_prompt, prompt)


class SkillRegistry:
    def __init__(self, skill_root: Path) -> None:
        self.skill_root = skill_root
        self._skills: dict[str, Skill] = {}

    def load(self) -> None:
        self._skills.clear()
        for metadata_path in self.skill_root.glob("*/skill.yaml"):
            with metadata_path.open("r", encoding="utf-8") as file:
                metadata = SkillMetadata.model_validate(yaml.safe_load(file))
            if not metadata.enabled:
                continue
            self._skills[metadata.name] = PromptSkill(metadata)

    def for_content(self, content_type: ContentType, platform: str | None = None) -> list[Skill]:
        exact_platform_matches = []
        generic_matches = []
        for skill in self._skills.values():
            supports_content = content_type in skill.metadata.content_types
            if not supports_content:
                continue
            if platform and platform in skill.metadata.platforms:
                exact_platform_matches.append(skill)
            elif not skill.metadata.platforms:
                generic_matches.append(skill)
        if platform and exact_platform_matches:
            return exact_platform_matches
        return generic_matches

    def get(self, name: str) -> Skill:
        return self._skills[name]

    def names(self) -> list[str]:
        return sorted(self._skills)
