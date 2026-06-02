from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from backend.app.domain.models import ContentType, ReviewStatus, SkillProposal
from backend.app.memory.store import MemoryStore


class SkillEvolutionAgent:
    def __init__(self, memory: MemoryStore, draft_root: Path) -> None:
        self.memory = memory
        self.draft_root = draft_root

    def propose(
        self,
        title: str,
        reason: str,
        proposed_skill_name: str,
        draft_prompt: str,
        content_types: list[ContentType],
        platforms: list[str],
    ) -> SkillProposal:
        proposal = SkillProposal(
            title=title,
            reason=reason,
            proposed_skill_name=_safe_skill_name(proposed_skill_name),
            draft_prompt=draft_prompt,
            content_types=content_types,
            platforms=platforms,
        )
        self.memory.store_skill_proposal(proposal)
        return proposal

    def approve(self, proposal_id: str, note: str | None = None) -> SkillProposal | None:
        proposal = self.memory.get_skill_proposal(proposal_id)
        if not proposal:
            return None
        proposal.status = ReviewStatus.APPROVED
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = note
        proposal.draft_skill_path = str(self._write_disabled_skill_draft(proposal))
        self.memory.update_skill_proposal(proposal)
        return proposal

    def reject(self, proposal_id: str, reason: str) -> SkillProposal | None:
        proposal = self.memory.get_skill_proposal(proposal_id)
        if not proposal:
            return None
        proposal.status = ReviewStatus.REJECTED
        proposal.reviewed_at = datetime.now(UTC)
        proposal.review_note = reason
        self.memory.update_skill_proposal(proposal)
        return proposal

    def discover_proposals(self) -> list[SkillProposal]:
        proposals: list[SkillProposal] = []
        existing_names = {
            proposal.proposed_skill_name
            for proposal in self.memory.list_skill_proposals()
            if proposal.status == ReviewStatus.PENDING_REVIEW
        }
        for proposal in self._discover_failure_proposals(existing_names):
            self.memory.store_skill_proposal(proposal)
            proposals.append(proposal)
        for proposal in self._discover_platform_volume_proposals(existing_names):
            self.memory.store_skill_proposal(proposal)
            proposals.append(proposal)
        return proposals

    def _discover_failure_proposals(self, existing_names: set[str]) -> list[SkillProposal]:
        proposals = []
        x_length_failures = [
            item
            for item in self.memory.list_failed_content(platform="x")
            if "280 characters" in " ".join(item.metadata.get("publish_validation_errors", []))
        ]
        if len(x_length_failures) >= 2 and "x_thread_compressor" not in existing_names:
            proposals.append(
                SkillProposal(
                    title="X thread compressor",
                    reason=(
                        "Repeated X publishing validation failures show posts exceeding "
                        "the 280 character limit."
                    ),
                    proposed_skill_name="x_thread_compressor",
                    draft_prompt=(
                        "Rewrite these source articles into an X thread where every post is "
                        "under 260 characters, keeps technical accuracy, and preserves a clear "
                        "hook and practical ending.\n\n{articles}"
                    ),
                    content_types=[ContentType.DAILY_SUMMARY, ContentType.HOT_TOPIC_ANALYSIS],
                    platforms=["x"],
                )
            )
        return proposals

    def _discover_platform_volume_proposals(self, existing_names: set[str]) -> list[SkillProposal]:
        proposals = []
        by_platform: dict[str, int] = {}
        for item in self.memory.list_content():
            by_platform[item.platform] = by_platform.get(item.platform, 0) + 1
        for platform, count in by_platform.items():
            proposal_name = f"{platform}_quality_reviewer"
            if count >= 5 and proposal_name not in existing_names:
                proposals.append(
                    SkillProposal(
                        title=f"{platform} quality reviewer",
                        reason=(
                            f"{platform} has {count} generated items. A review skill can "
                            "codify repeated human edits and platform-specific quality checks."
                        ),
                        proposed_skill_name=proposal_name,
                        draft_prompt=(
                            "Review these generated content drafts for platform fit, factual "
                            "grounding, repetition, and clarity. Return concise improvement "
                            "notes before publishing.\n\n{articles}"
                        ),
                        content_types=list(ContentType),
                        platforms=[platform],
                    )
                )
        return proposals

    def _write_disabled_skill_draft(self, proposal: SkillProposal) -> Path:
        skill_dir = self.draft_root / proposal.proposed_skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "skill.yaml"
        metadata = {
            "name": proposal.proposed_skill_name,
            "version": "0.1.0",
            "enabled": False,
            "description": proposal.title,
            "content_types": [content_type.value for content_type in proposal.content_types],
            "platforms": proposal.platforms,
            "system_prompt": "You are a careful technical content automation skill.",
            "user_prompt_template": proposal.draft_prompt,
        }
        with skill_path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(metadata, file, sort_keys=False, allow_unicode=True)
        return skill_path


def _safe_skill_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError("skill name must contain at least one letter or number")
    return normalized
