from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.app.agents.content_agent import ContentAgent
from backend.app.agents.growth_agent import GrowthAgent
from backend.app.agents.knowledge_ingestion_agent import KnowledgeIngestionAgent
from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.agents.reflection_agent import ReflectionAgent
from backend.app.agents.runtime import OpenSkaldAgentRuntime
from backend.app.agents.skill_evolution_agent import SkillEvolutionAgent
from backend.app.config.settings import AppConfig, ConfigIssue, load_config, validate_config
from backend.app.domain.models import GeneratedContent
from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
from backend.app.llm.provider import build_llm_provider
from backend.app.memory.store import MemoryStore
from backend.app.publishers.base import PublisherRegistry
from backend.app.scheduler.jobs import build_scheduler
from backend.app.skills.base import SkillRegistry


@dataclass
class AppContainer:
    config: AppConfig
    knowledge_base: OpenVikingKnowledgeBase
    skills: SkillRegistry
    publishers: PublisherRegistry
    memory: MemoryStore
    knowledge_ingestion_agent: KnowledgeIngestionAgent
    agent: ContentAgent
    publishing_agent: PublishingAgent
    skill_evolution_agent: SkillEvolutionAgent
    reflection_agent: ReflectionAgent
    growth_agent: GrowthAgent
    runtime: OpenSkaldAgentRuntime
    scheduler: AsyncIOScheduler
    config_issues: list[ConfigIssue]

    def generated_content_from_record(self, record: dict) -> GeneratedContent:
        return GeneratedContent.model_validate(record)

    def has_config_errors(self) -> bool:
        return any(issue.level == "error" for issue in self.config_issues)


def _build_agent_llm(config, key: str):
    """Build a per-agent LLM provider, falling back to global config."""
    partial = getattr(config.agent_llm, key, None)
    if partial:
        overrides = partial.model_dump(exclude_none=True)
        if overrides:
            merged = config.llm.model_copy(update=overrides)
            return build_llm_provider(merged)
    return build_llm_provider(config.llm)


def build_container(config_path: str | None = None) -> AppContainer:
    config = load_config(config_path)
    config_issues = validate_config(config)
    knowledge_base = OpenVikingKnowledgeBase(config.openviking)
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    publishers = PublisherRegistry(config.publishers)
    publishers.load()
    content_llm = _build_agent_llm(config, "content")
    reflection_llm = _build_agent_llm(config, "reflection")
    writing_llm = _build_agent_llm(config, "writing")
    memory = MemoryStore(
        config.memory.storage_path,
        config.memory.skill_proposals_path,
        config.memory.article_index_path,
    )
    knowledge_ingestion_agent = KnowledgeIngestionAgent(knowledge_base, memory)
    agent = ContentAgent(knowledge_base, skills, content_llm, memory)
    publishing_agent = PublishingAgent(memory, publishers)
    skill_evolution_agent = SkillEvolutionAgent(memory, Path("backend/app/skills"))
    reflection_agent = ReflectionAgent(memory, reflection_llm)
    growth_agent = GrowthAgent(memory)
    runtime = OpenSkaldAgentRuntime(
        content_agent=agent,
        publishing_agent=publishing_agent,
        reflection_agent=reflection_agent,
        growth_agent=growth_agent,
        skill_evolution_agent=skill_evolution_agent,
        memory=memory,
        writing_llm=writing_llm,
    )
    scheduler = build_scheduler(
        agent,
        publishing_agent,
        knowledge_ingestion_agent,
        config.scheduler,
    )
    return AppContainer(
        config,
        knowledge_base,
        skills,
        publishers,
        memory,
        knowledge_ingestion_agent,
        agent,
        publishing_agent,
        skill_evolution_agent,
        reflection_agent,
        growth_agent,
        runtime,
        scheduler,
        config_issues,
    )
