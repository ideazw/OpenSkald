from __future__ import annotations

from pathlib import Path

from backend.app import cli
from backend.app.agents.skill_evolution_agent import SkillEvolutionAgent
from backend.app.domain.models import (
    Article,
    ContentType,
    MemoryRecord,
    ReviewStatus,
    SkillProposal,
)
from backend.app.memory.store import MemoryStore


def test_content_agent_records_single_consolidated_failed_experience(tmp_path: Path) -> None:
    import asyncio
    from types import SimpleNamespace

    from backend.app.agents.content_agent import ContentAgent
    from backend.app.config.settings import OpenVikingConfig
    from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
    from backend.app.llm.provider import DemoLLMProvider

    class FailingSkill:
        metadata = SimpleNamespace(name="failing_skill")

        async def run(self, articles, llm):
            raise RuntimeError("model unavailable")

    class FailingSkillRegistry:
        def for_content(self, content_type, platform):
            return [FailingSkill()]

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    memory.remember_article(
        Article(id="article-1", title="Agent Memory", content="Memory matters.")
    )
    agent = ContentAgent(
        OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge)),
        FailingSkillRegistry(),
        DemoLLMProvider(),
        memory,
    )

    generated = asyncio.run(agent.generate(ContentType.DAILY_SUMMARY, ["x"]))

    assert generated == []
    experiences = memory.list_experiences()
    generate_experiences = [
        item for item in experiences if item.payload.get("action") == "generate"
    ]
    assert len(generate_experiences) == 1
    assert generate_experiences[0].payload["result"] == "failure"
    assert generate_experiences[0].payload["generated_count"] == 0
    assert generate_experiences[0].payload["errors"] == [
        "x/failing_skill: model unavailable"
    ]


def test_cli_review_approve_records_experience(tmp_path: Path, capsys) -> None:
    """CLI review-approve should write experience record."""
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        f"""
environment: test
log_level: INFO
llm:
  provider: demo
  model: demo-local-deterministic
openviking:
  knowledge_base_path: {knowledge}
publishers:
  x:
    enabled: true
    dry_run: true
memory:
  storage_path: {tmp_path / "memory.jsonl"}
  skill_proposals_path: {tmp_path / "skill_proposals.jsonl"}
scheduler: {{}}
""",
        encoding="utf-8",
    )
    container = cli.build_container(str(config_path))
    item = container.generated_content_from_record(
        {
            "content_type": "daily_summary",
            "platform": "x",
            "title": "Approve Me",
            "body": "1/ Ready",
        }
    )
    container.memory.remember_content(item)

    cli.main(["--config", str(config_path), "review-approve", "--content-id", item.id])

    experiences = container.memory.search_namespace(
        namespace="viking://agent/experience", kind="experience"
    )
    assert len(experiences) >= 1
    approve_exps = [e for e in experiences if e.payload.get("action") == "approve"]
    assert len(approve_exps) >= 1


def test_cli_review_reject_records_experience(tmp_path: Path, capsys) -> None:
    """CLI review-reject should write experience record with reason."""
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        f"""
environment: test
log_level: INFO
llm:
  provider: demo
  model: demo-local-deterministic
openviking:
  knowledge_base_path: {knowledge}
publishers:
  x:
    enabled: true
    dry_run: true
memory:
  storage_path: {tmp_path / "memory.jsonl"}
  skill_proposals_path: {tmp_path / "skill_proposals.jsonl"}
scheduler: {{}}
""",
        encoding="utf-8",
    )
    container = cli.build_container(str(config_path))
    item = container.generated_content_from_record(
        {
            "content_type": "daily_summary",
            "platform": "x",
            "title": "Reject Me",
            "body": "1/ Not good",
        }
    )
    container.memory.remember_content(item)

    cli.main(
        [
            "--config",
            str(config_path),
            "review-reject",
            "--content-id",
            item.id,
            "--reason",
            "Too short",
        ]
    )

    experiences = container.memory.search_namespace(
        namespace="viking://agent/experience", kind="experience"
    )
    reject_exps = [e for e in experiences if e.payload.get("action") == "reject"]
    assert len(reject_exps) >= 1
    assert "Too short" in str(reject_exps[0].payload.get("errors", []))


def test_skill_evolution_discover_from_reflections(tmp_path: Path) -> None:
    """SkillEvolutionAgent should create reflection-based skill proposals."""
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")

    # Pre-populate reflections that should trigger a proposal
    for i in range(3):
        memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/reflections",
                kind="reflection",
                payload={
                    "observation": f"Quality issue {i}",
                    "lesson": "Quality checks need improvement for platform-specific content",
                    "recommendation": "Add a platform-specific quality review step",
                    "confidence": 0.8,
                    "evidence_ids": [f"evt-{i}"],
                },
                source="test",
            )
        )

    agent = SkillEvolutionAgent(memory, tmp_path / "skills")
    proposals = agent.discover_proposals()

    reflection_proposals = [
        p for p in proposals if "reflection" in p.proposed_skill_name
    ]
    assert len(reflection_proposals) >= 1


def test_growth_propose_skills_creates_proposals(tmp_path: Path) -> None:
    """GrowthAgent.propose_skills should create SkillProposal objects."""
    from backend.app.agents.growth_agent import GrowthAgent

    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")

    # Populate some experiences to trigger skill proposals
    for i in range(3):
        memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/experience",
                kind="experience",
                payload={
                    "action": "publish",
                    "result": "failure",
                    "errors": [f"Error {i}"],
                },
                source="test",
            )
        )

    # Populate some reflections
    for i in range(5):
        memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/reflections",
                kind="reflection",
                payload={
                    "observation": f"Reflection {i}",
                    "lesson": f"Lesson {i}",
                    "recommendation": "Improve process",
                    "confidence": 0.7,
                    "evidence_ids": [f"id-{i}"],
                },
                source="test",
            )
        )

    agent = GrowthAgent(memory)
    proposals = []
    import asyncio
    proposals = asyncio.run(agent.propose_skills())

    assert len(proposals) > 0
    for p in proposals:
        assert isinstance(p, SkillProposal)
        assert p.status == ReviewStatus.PENDING_REVIEW


def test_orchestrator_max_turns_limits_loop(tmp_path: Path) -> None:
    """Orchestrator should respect max_turns and stop when exceeded."""
    import asyncio

    from backend.app.agents.growth_agent import GrowthAgent
    from backend.app.agents.orchestrator import MultiAgentOrchestrator
    from backend.app.agents.publishing_agent import PublishingAgent
    from backend.app.agents.reflection_agent import ReflectionAgent
    from backend.app.agents.research_agent import ResearchAgent
    from backend.app.agents.review_agent import ReviewAgent
    from backend.app.agents.writing_agent import WritingAgent
    from backend.app.config.settings import OpenVikingConfig
    from backend.app.knowledge.openviking import OpenVikingKnowledgeBase
    from backend.app.llm.provider import DemoLLMProvider
    from backend.app.publishers.base import PublisherRegistry
    from backend.app.skills.base import SkillRegistry

    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    skills = SkillRegistry(Path("backend/app/skills"))
    skills.load()
    llm = DemoLLMProvider()

    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    (knowledge_path / "t.md").write_text(
        "---\ntitle: T\n---\nContent.", encoding="utf-8"
    )

    orchestrator = MultiAgentOrchestrator(
        research_agent=ResearchAgent(
            OpenVikingKnowledgeBase(OpenVikingConfig(knowledge_base_path=knowledge_path)),
            memory,
        ),
        writing_agent=WritingAgent(skills, llm),
        review_agent=ReviewAgent(memory),
        publishing_agent=PublishingAgent(memory, PublisherRegistry({})),
        reflection_agent=ReflectionAgent(memory, llm),
        growth_agent=GrowthAgent(memory),
        memory=memory,
    )

    # Run with max_turns=1 - only research should execute
    result = asyncio.run(
        orchestrator.run(
            objective="Test",
            content_type=ContentType.DAILY_SUMMARY,
            platforms=["blog"],
            max_turns=1,
            require_review=True,
        )
    )

    # With max_turns=1, only Step 1 (Research) should execute
    assert len(result.artifacts) >= 1
    assert result.artifacts[0]["type"] == "source_brief"
