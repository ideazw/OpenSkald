from __future__ import annotations

from backend.app.domain.models import (
    AgentMetric,
    AgentReflection,
    ContentType,
    MemoryRecord,
    ReviewStatus,
    SkillProposal,
)
from backend.app.memory.store import MemoryStore


class GrowthAgent:
    """Consumes metrics and reflections to propose strategy improvements."""

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    async def analyze(self) -> list[AgentReflection]:
        """Analyze metrics and recent reflections to generate growth signals."""
        experiences = self.memory.list_experiences(limit=20)
        content = self.memory.list_content()
        signals: list[AgentReflection] = []

        # Identify repeated failure patterns
        failure_counts: dict[str, int] = {}
        for exp in experiences:
            payload = exp.payload
            if payload.get("result") == "failure":
                action = payload.get("action", "unknown")
                failure_counts[action] = failure_counts.get(action, 0) + 1

        for action, count in failure_counts.items():
            if count >= 2:
                ref = AgentReflection(
                    observation=(
                        f"Action '{action}' has failed {count} times. "
                        "This indicates a systemic issue."
                    ),
                    lesson=(
                        "Repeated failures in the same action type suggest that "
                        "validation or preconditions are insufficient."
                    ),
                    recommendation=(
                        f"Add preflight checks before '{action}' and review "
                        "the error handling in the relevant agent."
                    ),
                    confidence=min(0.5 + count * 0.1, 0.9),
                    evidence_ids=[
                        e.id
                        for e in experiences
                        if e.payload.get("result") == "failure"
                        and e.payload.get("action") == action
                    ],
                )
                self._store_reflection(ref)
                signals.append(ref)

        # Publishing success rate signal
        total = len(content)
        published = len([c for c in content if c.status == ReviewStatus.PUBLISHED])
        if total > 0:
            rate = published / total
            if rate < 0.5 and total >= 3:
                ref = AgentReflection(
                    observation=(
                        f"Publishing success rate is {rate:.0%} ({published}/{total}). "
                        "Below 50% indicates pipeline issues."
                    ),
                    lesson=(
                        "Low publishing success means content is getting stuck in "
                        "review or failing validation."
                    ),
                    recommendation="Audit the review and publishing pipeline for bottlenecks.",
                    confidence=0.7,
                )
                self._store_reflection(ref)
                signals.append(ref)
        return signals

    async def propose_skills(self) -> list[SkillProposal]:
        """Generate SkillProposal objects from growth analysis signals."""
        proposals: list[SkillProposal] = []
        existing_names = {
            p.proposed_skill_name
            for p in self.memory.list_skill_proposals()
            if p.status == ReviewStatus.PENDING_REVIEW
        }

        reflections = self.memory.list_reflections(limit=20)
        experiences = self.memory.list_experiences(limit=20)

        # Reflection volume signal
        if len(reflections) >= 5 and "growth_reflection_aggregator" not in existing_names:
            proposals.append(
                SkillProposal(
                    title="Growth reflection aggregator",
                    reason=(
                        f"With {len(reflections)} reflections stored, an aggregator skill "
                        "can summarize patterns across multiple reflections."
                    ),
                    proposed_skill_name="growth_reflection_aggregator",
                    draft_prompt=(
                        "Review these source articles and past agent reflections to produce "
                        "a consolidated growth strategy report.\n\n{articles}"
                    ),
                    content_types=list(ContentType),
                )
            )

        # Failure pattern signal
        failure_experiences = [
            e for e in experiences if e.payload.get("result") == "failure"
        ]
        if (
            len(failure_experiences) >= 3
            and "growth_failure_analyzer" not in existing_names
        ):
            proposals.append(
                SkillProposal(
                    title="Growth failure analyzer",
                    reason=(
                        f"Detected {len(failure_experiences)} failed experiences. "
                        "A dedicated failure analysis skill can identify root causes."
                    ),
                    proposed_skill_name="growth_failure_analyzer",
                    draft_prompt=(
                        "Analyze these source articles for potential failure modes and "
                        "propose mitigations before content generation.\n\n{articles}"
                    ),
                    content_types=list(ContentType),
                )
            )

        for proposal in proposals:
            self.memory.store_skill_proposal(proposal)
        return proposals

    async def import_metrics(self, metrics: list[AgentMetric]) -> int:
        """Import external metrics into memory for analysis."""
        count = 0
        for metric in metrics:
            self.memory.append_memory_record(
                MemoryRecord(
                    namespace="viking://agent/metrics",
                    kind="metric",
                    payload=metric.model_dump(mode="json"),
                    source="GrowthAgent",
                    confidence=1.0,
                )
            )
            count += 1

        # After importing metrics, run analysis
        await self.analyze()
        return count

    def _store_reflection(self, ref: AgentReflection) -> None:
        self.memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/reflections",
                kind="reflection",
                payload=ref.model_dump(mode="json"),
                source="GrowthAgent",
                confidence=ref.confidence,
            )
        )
