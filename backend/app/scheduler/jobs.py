from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.app.agents.content_agent import ContentAgent
from backend.app.agents.knowledge_ingestion_agent import KnowledgeIngestionAgent
from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.config.settings import SchedulerJobConfig
from backend.app.domain.models import ContentType


def build_scheduler(
    content_agent: ContentAgent,
    publishing_agent: PublishingAgent,
    knowledge_ingestion_agent: KnowledgeIngestionAgent,
    jobs: dict[str, SchedulerJobConfig],
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    for job_id, job in jobs.items():
        if not job.enabled:
            continue
        scheduled_callable = _scheduled_callable(
            content_agent,
            publishing_agent,
            knowledge_ingestion_agent,
            job,
        )
        minute, hour, day, month, day_of_week = job.cron.split()
        scheduler.add_job(
            scheduled_callable[0],
            "cron",
            id=job_id,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            args=scheduled_callable[1],
        )
    return scheduler


def _scheduled_callable(
    content_agent: ContentAgent,
    publishing_agent: PublishingAgent,
    knowledge_ingestion_agent: KnowledgeIngestionAgent,
    job: SchedulerJobConfig,
) -> tuple[object, list[object]]:
    if job.action == "generate":
        if not job.content_type:
            raise ValueError("generate scheduler jobs require content_type")
        return content_agent.generate, [ContentType(job.content_type), job.platforms]
    if job.action == "publish_approved":
        return publishing_agent.publish_approved, [job.platforms]
    if job.action == "ingest_knowledge":
        return knowledge_ingestion_agent.ingest, []
    raise ValueError(f"Unsupported scheduler action: {job.action}")
