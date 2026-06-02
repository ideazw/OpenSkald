from pathlib import Path

import yaml

from backend.app.agents.skill_evolution_agent import SkillEvolutionAgent
from backend.app.domain.models import ContentType, GeneratedContent, ReviewStatus
from backend.app.memory.store import MemoryStore
from backend.app.skills.base import SkillRegistry


def test_approved_skill_proposal_writes_disabled_draft(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    skill_root = tmp_path / "skills"
    agent = SkillEvolutionAgent(memory, skill_root)
    proposal = agent.propose(
        title="Architecture comparison writer",
        reason="Repeated comparison tasks",
        proposed_skill_name="Architecture Comparison Writer!",
        draft_prompt="Compare these articles.\n\n{articles}",
        content_types=[ContentType.DEEP_TECHNICAL_ANALYSIS],
        platforms=["wechat"],
    )

    approved = agent.approve(proposal.id, "Human approved as draft only")

    assert approved is not None
    assert approved.status == ReviewStatus.APPROVED
    assert approved.reviewed_at is not None
    assert approved.draft_skill_path is not None
    draft = yaml.safe_load(Path(approved.draft_skill_path).read_text(encoding="utf-8"))
    assert draft["name"] == "architecture_comparison_writer"
    assert draft["enabled"] is False


def test_registry_skips_disabled_generated_skill_drafts(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "disabled_writer"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.yaml").write_text(
        """
name: disabled_writer
version: 0.1.0
enabled: false
description: Disabled draft
content_types:
  - daily_summary
platforms:
  - x
system_prompt: Do not run.
user_prompt_template: "{articles}"
""",
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path / "skills")
    registry.load()

    assert registry.names() == []


def test_discover_proposes_x_thread_compressor_from_repeated_failures(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = SkillEvolutionAgent(memory, tmp_path / "skills")
    for index in range(2):
        memory.remember_content(
            GeneratedContent(
                content_type=ContentType.DAILY_SUMMARY,
                platform="x",
                title=f"Too long {index}",
                body="x" * 281,
                status=ReviewStatus.APPROVED,
                metadata={
                    "publish_validation_errors": [
                        "x posts exceed 280 characters at positions: [1]"
                    ]
                },
            )
        )

    proposals = agent.discover_proposals()

    assert len(proposals) == 1
    assert proposals[0].proposed_skill_name == "x_thread_compressor"
    assert proposals[0].status == ReviewStatus.PENDING_REVIEW
    assert not (tmp_path / "skills" / "x_thread_compressor" / "skill.yaml").exists()


def test_discover_does_not_duplicate_pending_proposals(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = SkillEvolutionAgent(memory, tmp_path / "skills")
    for index in range(2):
        memory.remember_content(
            GeneratedContent(
                content_type=ContentType.DAILY_SUMMARY,
                platform="x",
                title=f"Too long {index}",
                body="x" * 281,
                status=ReviewStatus.APPROVED,
                metadata={
                    "publish_validation_errors": [
                        "x posts exceed 280 characters at positions: [1]"
                    ]
                },
            )
        )

    first = agent.discover_proposals()
    second = agent.discover_proposals()

    assert len(first) == 1
    assert second == []
