from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.bootstrap import AppContainer


def operational_status(container: AppContainer) -> dict:
    config_errors = [issue for issue in container.config_issues if issue.level == "error"]
    scheduler_jobs = [
        {
            "id": job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        }
        for job in container.scheduler.get_jobs()
    ]
    return {
        "ok": not config_errors,
        "environment": container.config.environment,
        "config_issues": [issue.model_dump() for issue in container.config_issues],
        "scheduler": {
            "running": container.scheduler.running,
            "jobs": scheduler_jobs,
        },
        "knowledge": {
            "path": str(container.config.openviking.knowledge_base_path),
            "path_exists": container.config.openviking.knowledge_base_path.exists(),
            "indexed_articles": len(container.memory.list_articles()),
        },
        "memory": container.memory.operational_summary(),
        "skills": {
            "loaded": container.skills.names(),
        },
        "publishers": {
            platform: {
                "enabled": container.config.publishers[platform].enabled,
                "dry_run": container.config.publishers[platform].dry_run,
            }
            for platform in container.publishers.names()
        },
    }
