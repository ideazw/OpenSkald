from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from backend.app.domain.models import GeneratedContent, PublishResult, PublishValidationResult
from backend.app.publishers.base import Publisher


class PluginPublisher(Publisher):
    def validate(self, content: GeneratedContent) -> PublishValidationResult:
        result = super().validate(content)
        errors = list(result.errors)
        if not content.body.lstrip().startswith("#"):
            errors.append("blog content should be Markdown with a heading")
        if len(content.body) < 200:
            errors.append("blog post should be at least 200 characters")
        return PublishValidationResult(ok=not errors, errors=errors)

    async def publish(self, content: GeneratedContent) -> PublishResult:
        output_dir = Path(self.config.account_id or "./data/blog")
        slug = _slugify(content.title)
        file_path = output_dir / f"{slug}.md"

        if self.config.dry_run:
            return PublishResult(
                platform=self.platform,
                dry_run=True,
                content_id=content.id,
                title=content.title,
                url=str(file_path),
                metadata={"output_path": str(file_path)},
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        published_at = datetime.now(UTC).isoformat()
        file_path.write_text(
            (
                "---\n"
                f"title: {content.title}\n"
                f"date: {published_at}\n"
                "status: published\n"
                "---\n\n"
                f"{content.body.strip()}\n"
            ),
            encoding="utf-8",
        )
        return PublishResult(
            platform=self.platform,
            dry_run=False,
            content_id=content.id,
            external_id=slug,
            url=str(file_path),
            title=content.title,
            metadata={"output_path": str(file_path)},
        )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "untitled"
