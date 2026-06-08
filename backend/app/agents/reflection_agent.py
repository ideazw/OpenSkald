from __future__ import annotations

from typing import Any

from backend.app.domain.models import (
    AgentReflection,
    MemoryRecord,
    ReviewStatus,
)
from backend.app.llm.provider import LLMProvider
from backend.app.memory.store import MemoryStore


class ReflectionAgent:
    """Reads recent experiences and content outcomes, then produces structured reflections."""

    def __init__(self, memory: MemoryStore, llm: LLMProvider) -> None:
        self.memory = memory
        self.llm = llm

    async def discover(self) -> list[AgentReflection]:
        """Scan recent experiences and content to produce structured reflections."""
        experiences = self.memory.list_experiences(limit=50)
        content = self.memory.list_content()
        reflections: list[AgentReflection] = []

        # Reflection from failed experiences
        failed = [e for e in experiences if e.payload.get("result") == "failure"]
        for exp in failed[:5]:
            ref = await self._reflect_on_experience(exp)
            if ref:
                self._store_reflection(ref)
                reflections.append(ref)

        # Reflection from rejected content
        rejected = [c for c in content if c.status == ReviewStatus.REJECTED]
        for item in rejected[:3]:
            ref = await self._reflect_on_rejection(item)
            if ref:
                self._store_reflection(ref)
                reflections.append(ref)

        # Reflection from published content successes
        published = [c for c in content if c.status == ReviewStatus.PUBLISHED]
        for item in published[:3]:
            ref = await self._reflect_on_success(item)
            if ref:
                self._store_reflection(ref)
                reflections.append(ref)

        return reflections

    async def reflect_on_experiences(
        self, experiences: list[MemoryRecord]
    ) -> list[AgentReflection]:
        """Generate reflections from a specific set of experience records."""
        reflections = []
        for exp in experiences[:5]:
            ref = await self._reflect_on_experience(exp)
            if ref:
                self._store_reflection(ref)
                reflections.append(ref)
        return reflections

    def _store_reflection(self, ref: AgentReflection) -> None:
        self.memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/reflections",
                kind="reflection",
                payload=ref.model_dump(mode="json"),
                source="ReflectionAgent",
                confidence=ref.confidence,
            )
        )

    async def _reflect_on_experience(
        self, exp: MemoryRecord
    ) -> AgentReflection | None:
        payload = exp.payload
        action = payload.get("action", "unknown")
        errors = payload.get("errors", [])

        # Build deterministic reflection for demo/testing
        if errors:
            observation = (
                f"Action '{action}' failed with {len(errors)} error(s): "
                f"{'; '.join(errors[:2])}"
            )
            lesson = (
                f"Errors in '{action}' indicate that validation or preconditions "
                "need attention before retry."
            )
            recommendation = (
                f"Review the '{action}' configuration, fix validation issues, and retry. "
                "Consider adding preflight checks."
            )
        else:
            observation = f"Action '{action}' completed successfully."
            lesson = (
                f"The '{action}' workflow is functioning as expected. "
                "Monitor for gradual changes in output quality."
            )
            recommendation = "Continue routine operation. No immediate changes needed."

        return AgentReflection(
            observation=observation,
            lesson=lesson,
            recommendation=recommendation,
            confidence=0.7 if errors else 0.5,
            evidence_ids=[exp.id],
        )

    async def _reflect_on_rejection(
        self, item: Any
    ) -> AgentReflection | None:
        note = item.review_note or "No specific review note provided."
        observation = (
            f"Content '{item.title}' ({item.platform}, {item.content_type.value}) "
            f"was rejected: {note}"
        )
        lesson = (
            "Rejected content signals a gap between generated output and human "
            "quality expectations. Style, factual grounding, and platform tone need review."
        )
        recommendation = (
            f"Examine the review note for platform '{item.platform}' and adjust "
            "the writing skill prompt or add platform-specific quality checks."
        )
        return AgentReflection(
            observation=observation,
            lesson=lesson,
            recommendation=recommendation,
            confidence=0.8,
            evidence_ids=[item.id],
        )

    async def _reflect_on_success(self, item: Any) -> AgentReflection | None:
        observation = (
            f"Content '{item.title}' was successfully published on {item.platform}."
        )
        lesson = (
            "Successful publishing validates the current generation and review pipeline. "
            "Track engagement metrics to assess content quality objectively."
        )
        recommendation = (
            "Continue monitoring publish success rate. When enough success data exists, "
            "consider proposing a skill that codifies effective patterns."
        )
        return AgentReflection(
            observation=observation,
            lesson=lesson,
            recommendation=recommendation,
            confidence=0.6,
            evidence_ids=[item.id],
        )
