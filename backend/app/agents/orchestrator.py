from __future__ import annotations

from typing import Any

from backend.app.agents.growth_agent import GrowthAgent
from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.agents.reflection_agent import ReflectionAgent
from backend.app.agents.research_agent import ResearchAgent
from backend.app.agents.review_agent import ReviewAgent
from backend.app.agents.writing_agent import WritingAgent
from backend.app.domain.models import (
    AgentResult,
    ContentType,
    GeneratedContent,
    MemoryRecord,
    PlatformDraft,
    ReviewReport,
    ReviewStatus,
)
from backend.app.memory.store import MemoryStore


class MultiAgentOrchestrator:
    """Deterministic collaborative orchestration of specialist agents.

    Workflow:
      User objective
        -> ResearchAgent returns SourceBrief
        -> WritingAgent returns PlatformDraft[]
        -> ReviewAgent returns ReviewReport
        -> WritingAgent revises if needed
        -> Content stored as pending_review
        -> Human approves (external)
        -> PublishingAgent publishes
        -> ReflectionAgent records lessons
        -> GrowthAgent proposes skills/strategy
    """

    def __init__(
        self,
        research_agent: ResearchAgent,
        writing_agent: WritingAgent,
        review_agent: ReviewAgent,
        publishing_agent: PublishingAgent,
        reflection_agent: ReflectionAgent,
        growth_agent: GrowthAgent,
        memory: MemoryStore,
    ) -> None:
        self.research_agent = research_agent
        self.writing_agent = writing_agent
        self.review_agent = review_agent
        self.publishing_agent = publishing_agent
        self.reflection_agent = reflection_agent
        self.growth_agent = growth_agent
        self.memory = memory

    # pylint: disable=too-many-locals,too-many-statements
    async def run(
        self,
        objective: str,
        content_type: ContentType,
        platforms: list[str],
        max_turns: int = 8,
        require_review: bool = True,
    ) -> AgentResult:
        """Execute the full collaborative workflow."""
        artifacts: list[dict[str, Any]] = []
        memory_writes: list[MemoryRecord] = []
        errors: list[str] = []
        turn_count = 0

        # Step 1: Research
        turn_count += 1
        try:
            brief = await self.research_agent.research(objective)
            if not brief.articles:
                errors.append("No source articles found for research")
            artifacts.append(
                {"type": "source_brief", "data": brief.model_dump(mode="json")}
            )
            memory_writes.append(
                MemoryRecord(
                    namespace="viking://agent/plans",
                    kind="plan",
                    payload={
                        "objective": objective,
                        "article_count": len(brief.articles),
                    },
                    source="MultiAgentOrchestrator.research",
                )
            )
        except Exception as exc:
            errors.append(f"ResearchAgent failed: {exc}")

        if turn_count >= max_turns:
            return AgentResult(
                artifacts=artifacts, memory_writes=memory_writes, errors=errors
            )

        # Step 2: Writing
        turn_count += 1
        drafts: list[PlatformDraft] = []
        try:
            drafts = await self.writing_agent.write(brief, content_type, platforms)
            for draft in drafts:
                artifacts.append(
                    {
                        "type": "platform_draft",
                        "data": draft.model_dump(mode="json"),
                    }
                )
        except Exception as exc:
            errors.append(f"WritingAgent failed: {exc}")

        if turn_count >= max_turns:
            return AgentResult(
                artifacts=artifacts, memory_writes=memory_writes, errors=errors
            )

        # Step 3: Review (with optional revise)
        turn_count += 1
        review_reports: list[ReviewReport] = []
        if require_review:
            for draft in drafts:
                try:
                    report = await self.review_agent.review(draft)
                    review_reports.append(report)
                    artifacts.append(
                        {
                            "type": "review_report",
                            "data": report.model_dump(mode="json"),
                        }
                    )
                    if not report.approved:
                        errors.append(
                            f"Review failed for {draft.platform}: {report.revision_suggestions}"
                        )
                except Exception as exc:
                    errors.append(
                        f"ReviewAgent failed for {draft.platform}: {exc}"
                    )
                    review_reports.append(
                        ReviewReport(
                            approved=False,
                            notes=f"Review failed: {exc}",
                            factual_issues=[str(exc)],
                        )
                    )

            # One round of revision if review failed
            if (
                any(not r.approved for r in review_reports)
                and turn_count < max_turns
            ):
                turn_count += 1
                for idx, (draft, report) in enumerate(
                    zip(drafts, review_reports, strict=True)
                ):
                    if not report.approved:
                        fixed_body = draft.body
                        if "280 character" in str(report.platform_issues):
                            fixed_body = draft.body[:260]
                        if fixed_body != draft.body:
                            drafts[idx] = PlatformDraft(
                                platform=draft.platform,
                                title=draft.title,
                                body=fixed_body,
                                content_type=draft.content_type,
                                metadata={**draft.metadata, "revised": True},
                            )
                            artifacts.append(
                                {
                                    "type": "revised_draft",
                                    "data": drafts[idx].model_dump(mode="json"),
                                }
                            )

        if turn_count >= max_turns:
            return AgentResult(
                artifacts=artifacts, memory_writes=memory_writes, errors=errors
            )

        # Step 4: Store as pending_review content
        turn_count += 1
        for draft in drafts:
            content = GeneratedContent(
                content_type=draft.content_type,
                platform=draft.platform,
                title=draft.title,
                body=draft.body,
                metadata={
                    **draft.metadata,
                    "orchestrated": True,
                    "objective": objective,
                },
                status=ReviewStatus.PENDING_REVIEW,
            )
            self.memory.remember_content(content)
            artifacts.append(
                {"type": "stored_content", "data": content.model_dump(mode="json")}
            )

        if turn_count >= max_turns:
            return AgentResult(
                artifacts=artifacts, memory_writes=memory_writes, errors=errors
            )

        # Step 5: Reflection
        turn_count += 1
        try:
            experiences = self.memory.list_experiences(limit=10)
            reflections = await self.reflection_agent.reflect_on_experiences(
                experiences
            )
            for ref in reflections:
                memory_writes.append(
                    MemoryRecord(
                        namespace="viking://agent/reflections",
                        kind="reflection",
                        payload=ref.model_dump(mode="json"),
                        source="MultiAgentOrchestrator.reflection",
                        confidence=ref.confidence,
                    )
                )
        except Exception as exc:
            errors.append(f"ReflectionAgent failed: {exc}")

        if turn_count >= max_turns:
            return AgentResult(
                artifacts=artifacts, memory_writes=memory_writes, errors=errors
            )

        # Step 6: Growth analysis
        turn_count += 1
        try:
            growth_reflections = await self.growth_agent.analyze()
            for ref in growth_reflections:
                memory_writes.append(
                    MemoryRecord(
                        namespace="viking://agent/reflections",
                        kind="reflection",
                        payload=ref.model_dump(mode="json"),
                        source="MultiAgentOrchestrator.growth",
                        confidence=ref.confidence,
                    )
                )
        except Exception as exc:
            errors.append(f"GrowthAgent failed: {exc}")

        return AgentResult(
            artifacts=artifacts, memory_writes=memory_writes, errors=errors
        )
