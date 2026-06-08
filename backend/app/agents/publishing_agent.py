from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.app.domain.models import GeneratedContent, MemoryRecord, ReviewStatus
from backend.app.memory.store import MemoryStore
from backend.app.publishers.base import PublisherRegistry


class PublishingAgent:
    def __init__(self, memory: MemoryStore, publishers: PublisherRegistry) -> None:
        self.memory = memory
        self.publishers = publishers

    async def publish_approved(self, platforms: list[str] | None = None) -> list[dict]:
        target_platforms = set(platforms or self.publishers.names())
        results = []
        approved = self.memory.list_content(status=ReviewStatus.APPROVED)
        for content in approved:
            if content.platform not in target_platforms:
                continue
            result = await self.publish_content(content)
            if result:
                results.append(result)
        return results

    async def publish_content(self, content: GeneratedContent) -> dict | None:
        import time
        start = time.monotonic()
        publisher = self.publishers.get(content.platform)
        if not publisher.config.enabled:
            content.metadata["publish_validation_errors"] = [
                f"publisher {content.platform} is disabled"
            ]
            self.memory.update_content(content)
            self._record_experience(
                "publish", "failure", content.id,
                [f"publisher {content.platform} is disabled"],
            )
            return None
        validation = publisher.validate(content)
        if not validation.ok:
            content.metadata["publish_validation_errors"] = validation.errors
            self.memory.update_content(content)
            self._record_experience("publish", "failure", content.id, validation.errors)
            return None
        try:
            result = await publisher.publish(content)
        except Exception as error:
            self._record_publish_error(content, error)
            self._record_experience("publish", "failure", content.id, [str(error)])
            return None
        duration_ms = int((time.monotonic() - start) * 1000)
        content.status = ReviewStatus.PUBLISHED
        content.published_at = datetime.now(UTC)
        content.metadata["publish_result"] = result.model_dump(mode="json")
        self.memory.update_content(content)
        self._record_experience("publish", "success", content.id, [], duration_ms)
        return result.model_dump(mode="json")

    def validate_content(self, content: GeneratedContent) -> list[str]:
        publisher = self.publishers.get(content.platform)
        return publisher.validate(content).errors

    def _record_experience(
        self, action: str, result: str, content_id: str,
        errors: list[str] | None = None, duration_ms: int = 0,
    ) -> None:
        self.memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/experience",
                kind="experience",
                payload={
                    "action": action,
                    "result": result,
                    "content_ids": [content_id],
                    "errors": errors or [],
                    "duration_ms": duration_ms,
                },
                source="PublishingAgent",
            )
        )

    def _record_publish_error(self, content: GeneratedContent, error: Exception) -> None:
        error_record: dict[str, Any] = {
            "at": datetime.now(UTC).isoformat(),
            "type": type(error).__name__,
            "message": str(error),
        }
        errors = content.metadata.get("publish_errors", [])
        if not isinstance(errors, list):
            errors = []
        errors.append(error_record)
        content.metadata["last_publish_error"] = error_record
        content.metadata["publish_errors"] = errors[-10:]
        self.memory.update_content(content)
