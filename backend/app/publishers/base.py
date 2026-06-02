from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module

from backend.app.config.settings import PublisherConfig
from backend.app.domain.models import GeneratedContent, PublishResult, PublishValidationResult


class Publisher(ABC):
    platform: str

    def __init__(self, config: PublisherConfig) -> None:
        self.config = config

    def validate(self, content: GeneratedContent) -> PublishValidationResult:
        errors = []
        if content.platform != self.platform:
            errors.append(f"content platform is {content.platform}, expected {self.platform}")
        if not content.title.strip():
            errors.append("title is required")
        if not content.body.strip():
            errors.append("body is required")
        return PublishValidationResult(ok=not errors, errors=errors)

    async def check(self) -> dict:
        return {
            "platform": self.platform,
            "ok": True,
            "dry_run": self.config.dry_run,
            "enabled": self.config.enabled,
        }

    @abstractmethod
    async def publish(self, content: GeneratedContent) -> PublishResult:
        """Publish generated content or perform a dry run."""


class DryRunPublisher(Publisher):
    async def publish(self, content: GeneratedContent) -> PublishResult:
        return PublishResult(
            platform=self.platform,
            dry_run=True,
            content_id=content.id,
            title=content.title,
            metadata={"account_id": self.config.account_id},
        )


class PublisherRegistry:
    def __init__(self, configs: dict[str, PublisherConfig]) -> None:
        self.configs = configs
        self._publishers: dict[str, Publisher] = {}

    def load(self) -> None:
        self._publishers.clear()
        for platform, config in self.configs.items():
            module = import_module(f"backend.app.publishers.{platform}.publisher")
            publisher_class = module.PluginPublisher
            publisher = publisher_class(config)
            publisher.platform = platform
            self._publishers[platform] = publisher

    def get(self, platform: str) -> Publisher:
        return self._publishers[platform]

    def names(self) -> list[str]:
        return sorted(self._publishers)
