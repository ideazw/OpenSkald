from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    model: str = "deepseek-v4-flash"
    timeout_seconds: float = 60


class OpenVikingConfig(BaseModel):
    knowledge_base_path: Path = Path("./knowledge")
    include_globs: list[str] = Field(default_factory=lambda: ["**/*.md", "**/*.txt"])
    max_articles_per_run: int = 10


class SchedulerJobConfig(BaseModel):
    enabled: bool = True
    cron: str
    action: str = "generate"
    content_type: str | None = None
    platforms: list[str] = Field(default_factory=list)


class PublisherConfig(BaseModel):
    enabled: bool = False
    account_id: str | None = None
    dry_run: bool = True
    credentials_env: str | None = None


class ReviewConfig(BaseModel):
    require_human_approval: bool = True
    storage_path: Path = Path("./data/review_queue.jsonl")


class MemoryConfig(BaseModel):
    storage_path: Path = Path("./data/memory.jsonl")
    skill_proposals_path: Path = Path("./data/skill_proposals.jsonl")
    article_index_path: Path = Path("./data/articles.jsonl")


class AppConfig(BaseModel):
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    openviking: OpenVikingConfig = Field(default_factory=OpenVikingConfig)
    scheduler: dict[str, SchedulerJobConfig] = Field(default_factory=dict)
    publishers: dict[str, PublisherConfig] = Field(default_factory=dict)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)


class ConfigIssue(BaseModel):
    level: Literal["warning", "error"]
    message: str


REQUIRED_PUBLISHER_CREDENTIALS = {
    "wechat": ["app_id", "app_secret", "thumb_media_id"],
    "xiaohongshu": ["cookie"],
}


def validate_config(config: AppConfig) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    knowledge_base_path = config.openviking.knowledge_base_path
    if knowledge_base_path == Path("."):
        issues.append(
            ConfigIssue(
                level="error",
                message=(
                    "OpenViking knowledge base path cannot be empty or point to "
                    "the current directory."
                ),
            )
        )
    elif not knowledge_base_path.exists():
        issues.append(
            ConfigIssue(
                level="warning",
                message=(
                    "OpenViking knowledge base path does not exist yet: "
                    f"{knowledge_base_path}"
                ),
            )
        )
    if config.llm.model == "configured-in-config-yaml":
        issues.append(ConfigIssue(level="warning", message="LLM model is still the default value"))
    if config.environment == "production" and config.llm.api_key_env not in os.environ:
        issues.append(
            ConfigIssue(
                level="error",
                message=f"Missing production LLM API key env var: {config.llm.api_key_env}",
            )
        )
    if config.environment == "production" and not config.review.require_human_approval:
        issues.append(
            ConfigIssue(
                level="error",
                message="Production requires human approval before publishing",
            )
        )
    for job_name, job in config.scheduler.items():
        if job.action == "generate" and not job.content_type:
            issues.append(
                ConfigIssue(
                    level="error",
                    message=f"Scheduler job {job_name} requires content_type",
                )
            )
        if job.action not in {"generate", "publish_approved", "ingest_knowledge"}:
            issues.append(
                ConfigIssue(
                    level="error",
                    message=f"Scheduler job {job_name} has unsupported action: {job.action}",
                )
            )
    for platform, publisher in config.publishers.items():
        if config.environment == "production" and publisher.enabled and publisher.dry_run:
            issues.append(
                ConfigIssue(
                    level="warning",
                    message=f"Publisher {platform} is enabled but still running in dry-run mode",
                )
            )
        if config.environment == "production" and publisher.enabled and not publisher.dry_run:
            if platform == "blog" and not publisher.account_id:
                issues.append(
                    ConfigIssue(
                        level="error",
                        message="Production blog publisher requires account_id output directory",
                    )
                )
            if platform != "blog":
                if not publisher.credentials_env:
                    issues.append(
                        ConfigIssue(
                            level="error",
                            message=f"Publisher {platform} requires credentials_env",
                        )
                    )
                elif publisher.credentials_env not in os.environ:
                    issues.append(
                        ConfigIssue(
                            level="error",
                            message=(
                                f"Missing credentials env var for publisher {platform}: "
                                f"{publisher.credentials_env}"
                            ),
                        )
                    )
                else:
                    issues.extend(_validate_publisher_secret(platform, publisher.credentials_env))
    return issues


def _validate_publisher_secret(platform: str, env_name: str) -> list[ConfigIssue]:
    raw = os.getenv(env_name, "")
    try:
        secret = json.loads(raw)
    except json.JSONDecodeError:
        return [
            ConfigIssue(
                level="error",
                message=f"Publisher {platform} credentials env var is not valid JSON: {env_name}",
            )
        ]
    if not isinstance(secret, dict):
        return [
            ConfigIssue(
                level="error",
                message=(
                    f"Publisher {platform} credentials env var must be a JSON object: "
                    f"{env_name}"
                ),
            )
        ]
    missing = [
        key for key in REQUIRED_PUBLISHER_CREDENTIALS.get(platform, []) if not secret.get(key)
    ]
    if platform == "x":
        missing = _missing_x_credentials(secret)
    if missing:
        return [
            ConfigIssue(
                level="error",
                message=(
                    f"Publisher {platform} credentials env var {env_name} is missing keys: "
                    f"{', '.join(missing)}"
                ),
            )
        ]
    return []


def _missing_x_credentials(secret: dict[str, Any]) -> list[str]:
    if secret.get("user_access_token"):
        return []
    required_aliases = {
        "consumer_key": ("consumer_key", "api_key", "oauth_consumer_key"),
        "consumer_secret": (
            "consumer_secret",
            "api_secret",
            "api_key_secret",
            "oauth_consumer_secret",
        ),
        "access_token": ("access_token", "oauth_token"),
        "access_token_secret": ("access_token_secret", "oauth_token_secret"),
    }
    return [
        target
        for target, aliases in required_aliases.items()
        if not any(secret.get(alias) for alias in aliases)
    ]


def config_summary(config: AppConfig, issues: list[ConfigIssue] | None = None) -> dict[str, Any]:
    return {
        "environment": config.environment,
        "log_level": config.log_level,
        "llm": {
            "provider": config.llm.provider,
            "base_url": config.llm.base_url,
            "model": config.llm.model,
            "api_key_env": config.llm.api_key_env,
            "api_key_configured": config.llm.api_key_env in os.environ,
            "timeout_seconds": config.llm.timeout_seconds,
        },
        "openviking": {
            "knowledge_base_path": str(config.openviking.knowledge_base_path),
            "knowledge_base_exists": config.openviking.knowledge_base_path.exists(),
            "include_globs": config.openviking.include_globs,
            "max_articles_per_run": config.openviking.max_articles_per_run,
        },
        "scheduler_jobs": {
            name: {
                "enabled": job.enabled,
                "cron": job.cron,
                "action": job.action,
                "content_type": job.content_type,
                "platforms": job.platforms,
            }
            for name, job in config.scheduler.items()
        },
        "publishers": {
            platform: {
                "enabled": publisher.enabled,
                "dry_run": publisher.dry_run,
                "account_id_configured": bool(publisher.account_id),
                "credentials_env": publisher.credentials_env,
                "credentials_configured": (
                    publisher.credentials_env in os.environ if publisher.credentials_env else False
                ),
            }
            for platform, publisher in config.publishers.items()
        },
        "review": {
            "require_human_approval": config.review.require_human_approval,
            "storage_path": str(config.review.storage_path),
        },
        "memory": {
            "storage_path": str(config.memory.storage_path),
            "skill_proposals_path": str(config.memory.skill_proposals_path),
            "article_index_path": str(config.memory.article_index_path),
        },
        "issues": [issue.model_dump() for issue in (issues or validate_config(config))],
    }


def load_config(path: str | Path | None = None) -> AppConfig:
    env_path = os.getenv("OPENVIKING_AGENT_CONFIG")
    specified_path = path if path is not None else env_path
    config_path = Path(specified_path) if specified_path is not None else Path("config/config.yaml")
    if not config_path.exists():
        if specified_path is not None:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        return AppConfig()
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    return AppConfig.model_validate(raw)


def resolve_secret(env_name: str | None) -> str | None:
    if not env_name:
        return None
    return os.getenv(env_name)
