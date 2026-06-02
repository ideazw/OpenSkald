from backend.app.agents.content_agent import ContentAgent
from backend.app.agents.knowledge_ingestion_agent import KnowledgeIngestionAgent
from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.config.settings import SchedulerJobConfig
from backend.app.domain.models import ContentType
from backend.app.scheduler.jobs import build_scheduler


def test_scheduler_loads_enabled_cron_jobs() -> None:
    scheduler = build_scheduler(
        content_agent=ContentAgent.__new__(ContentAgent),
        publishing_agent=PublishingAgent.__new__(PublishingAgent),
        knowledge_ingestion_agent=KnowledgeIngestionAgent.__new__(KnowledgeIngestionAgent),
        jobs={
            "ingest": SchedulerJobConfig(
                enabled=True,
                cron="*/30 * * * *",
                action="ingest_knowledge",
            ),
            "daily": SchedulerJobConfig(
                enabled=True,
                cron="0 9 * * *",
                action="generate",
                content_type=ContentType.DAILY_SUMMARY.value,
                platforms=["x"],
            ),
            "disabled": SchedulerJobConfig(
                enabled=False,
                cron="0 10 * * *",
                action="generate",
                content_type=ContentType.WEEKLY_SUMMARY.value,
                platforms=["wechat"],
            ),
            "publish": SchedulerJobConfig(
                enabled=True,
                cron="*/15 * * * *",
                action="publish_approved",
                platforms=["x"],
            ),
        },
    )

    assert [job.id for job in scheduler.get_jobs()] == ["ingest", "daily", "publish"]
