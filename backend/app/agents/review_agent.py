from __future__ import annotations

from backend.app.domain.models import (
    GeneratedContent,
    PlatformDraft,
    ReviewReport,
)
from backend.app.memory.store import MemoryStore


class ReviewAgent:
    """Quality review agent with veto power over content releases."""

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    async def review(self, draft: PlatformDraft) -> ReviewReport:
        """Check a platform draft for quality, factual grounding, and platform rules."""
        platform_issues: list[str] = []
        factual_issues: list[str] = []
        notes: list[str] = []

        # Platform rule checks
        if draft.platform == "x" and len(draft.body) > 280:
            platform_issues.append("X posts exceed 280 character limit")

        if draft.platform in ("wechat", "blog") and len(draft.body) < 50:
            platform_issues.append("Content too short for long-form platform")

        # Content quality checks
        if not draft.title.strip():
            factual_issues.append("Title is empty")

        if len(draft.body.strip()) < 10:
            factual_issues.append("Body is too short to review")

        # Check for empty skills or error markers
        if "[Generation failed" in draft.body:
            factual_issues.append("Content generation reported an error")

        if platform_issues or factual_issues:
            notes.append(f"Review identified {len(platform_issues) + len(factual_issues)} issue(s)")

        approved = len(platform_issues) == 0 and len(factual_issues) == 0

        revision_suggestions = ""
        if not approved:
            suggestions = []
            if platform_issues:
                suggestions.append(f"Fix platform issues: {'; '.join(platform_issues)}")
            if factual_issues:
                suggestions.append(f"Fix content issues: {'; '.join(factual_issues)}")
            revision_suggestions = "; ".join(suggestions)

        return ReviewReport(
            approved=approved,
            notes="; ".join(notes),
            revision_suggestions=revision_suggestions,
            platform_issues=platform_issues,
            factual_issues=factual_issues,
        )

    async def review_content(
        self, content: GeneratedContent
    ) -> ReviewReport:
        """Review already-generated content from memory."""
        draft = PlatformDraft(
            platform=content.platform,
            title=content.title,
            body=content.body,
            content_type=content.content_type,
            metadata=content.metadata,
        )
        return await self.review(draft)
