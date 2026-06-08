from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.bootstrap import AppContainer
from backend.app.config.settings import config_summary
from backend.app.domain.models import AgentMetric, AgentMode, ContentType, ReviewStatus
from backend.app.llm.provider import LLMProviderError
from backend.app.ops.status import operational_status

router = APIRouter()
STATUS_QUERY = Query(default=None)
PLATFORM_QUERY = Query(default=None)
LIMIT_QUERY = Query(default=20, ge=1, le=100)
QUERY_PARAM = Query(default="")


class GenerateRequest(BaseModel):
    content_type: ContentType
    platforms: list[str]


class RejectRequest(BaseModel):
    reason: str


class SkillProposalRequest(BaseModel):
    title: str
    reason: str
    proposed_skill_name: str
    draft_prompt: str
    content_types: list[ContentType]
    platforms: list[str] = []


class ApprovalRequest(BaseModel):
    note: str | None = None





class AgentRunRequest(BaseModel):
    objective: str
    content_type: ContentType
    platforms: list[str]
    mode: str = "single"


class MetricsImportRequest(BaseModel):
    metrics: list[AgentMetric]


def build_router(container: AppContainer) -> APIRouter:
    api = APIRouter()

    @api.get("/health")
    async def health() -> dict:
        return {
            "status": "degraded" if container.config_issues else "ok",
            "config_errors": [
                issue.message for issue in container.config_issues if issue.level == "error"
            ],
            "reflector": "ok",
            "skills": container.skills.names(),
            "publishers": container.publishers.names(),
            "scheduler_jobs": [job.id for job in container.scheduler.get_jobs()],
        }

    @api.get("/config/summary")
    async def get_config_summary() -> dict:
        return config_summary(container.config, container.config_issues)

    @api.get("/status")
    async def status() -> dict:
        return operational_status(container)

    @api.post("/generate")
    async def generate(request: GenerateRequest) -> list[dict]:
        try:
            content = await container.agent.generate(request.content_type, request.platforms)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except LLMProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return [item.model_dump(mode="json") for item in content]

    @api.post("/knowledge/ingest")
    async def ingest_knowledge() -> dict:
        return container.knowledge_ingestion_agent.ingest()

    @api.get("/knowledge/articles")
    async def knowledge_articles() -> list[dict]:
        return [article.model_dump(mode="json") for article in container.memory.list_articles()]

    @api.get("/knowledge/search")
    async def knowledge_search(q: str = QUERY_PARAM, limit: int = LIMIT_QUERY) -> list[dict]:
        return [
            article.model_dump(mode="json")
            for article in container.memory.search_articles(query=q, limit=limit)
        ]

    @api.get("/review")
    async def review_queue(
        status: ReviewStatus | None = STATUS_QUERY,
        platform: str | None = PLATFORM_QUERY,
    ) -> list[dict]:
        return [
            item.model_dump(mode="json")
            for item in container.memory.list_content(status=status, platform=platform)
        ]

    @api.get("/content/summary")
    async def content_summary() -> dict:
        return container.memory.content_summary()

    @api.get("/content/failures")
    async def content_failures(platform: str | None = PLATFORM_QUERY) -> list[dict]:
        return [
            item.model_dump(mode="json")
            for item in container.memory.list_failed_content(platform=platform)
        ]

    @api.get("/memory/timeline")
    async def memory_timeline(
        limit: int = LIMIT_QUERY,
        platform: str | None = PLATFORM_QUERY,
    ) -> list[dict]:
        return container.memory.timeline(limit=limit, platform=platform)

    @api.get("/memory/search")
    async def memory_search(q: str = QUERY_PARAM, limit: int = LIMIT_QUERY) -> list[dict]:
        return [
            item.model_dump(mode="json")
            for item in container.memory.search_content(query=q, limit=limit)
        ]

    @api.get("/memory/records")
    async def memory_records(
        namespace: str = Query(default="viking://"),
        kind: str | None = Query(default=None),
        limit: int = LIMIT_QUERY,
    ) -> list[dict]:
        return [
            r.model_dump(mode="json")
            for r in container.memory.search_namespace(namespace=namespace, kind=kind, limit=limit)
        ]

    @api.get("/memory/reflections")
    async def memory_reflections(limit: int = LIMIT_QUERY) -> list[dict]:
        return [
            r.model_dump(mode="json") for r in container.memory.list_reflections(limit=limit)
        ]

    @api.post("/memory/reflections/discover")
    async def discover_reflections() -> list[dict]:
        reflections = await container.reflection_agent.discover()
        return [ref.model_dump(mode="json") for ref in reflections]

    @api.post("/metrics/import")
    async def import_metrics(request: MetricsImportRequest) -> dict:
        count = await container.growth_agent.import_metrics(request.metrics)
        return {"ok": True, "imported": count}

    @api.post("/agent/runs")
    async def create_agent_run(request: AgentRunRequest) -> dict:
        mode = AgentMode.COLLABORATIVE if request.mode == "collaborative" else AgentMode.SINGLE
        run = await container.runtime.run(
            objective=request.objective,
            content_type=request.content_type,
            platforms=request.platforms,
            mode=mode,
        )
        return run.model_dump(mode="json")

    @api.get("/agent/runs")
    async def list_agent_runs(limit: int = LIMIT_QUERY) -> list[dict]:
        return container.runtime.list_runs(limit=limit)

    @api.get("/agent/runs/{run_id}")
    async def get_agent_run(run_id: str) -> dict:
        run = container.runtime.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="agent run not found")
        return run

    @api.post("/review/{content_id}/approve")
    async def approve(content_id: str) -> dict:
        content = container.memory.get_content(content_id)
        if not content:
            raise HTTPException(status_code=404, detail="content not found")
        content.status = ReviewStatus.APPROVED
        content.reviewed_at = datetime.now(UTC)
        content.review_note = None
        container.memory.update_content(content)
        # Record experience
        container.memory.append_memory_record(
            __import__("backend.app.domain.models", fromlist=["MemoryRecord"]).MemoryRecord(
                namespace="viking://agent/experience",
                kind="experience",
                payload={
                    "action": "approve",
                    "result": "success",
                    "content_ids": [content_id],
                },
                source="API.approve",
            )
        )
        return content.model_dump(mode="json")

    @api.post("/review/{content_id}/reject")
    async def reject(content_id: str, request: RejectRequest) -> dict:
        content = container.memory.get_content(content_id)
        if not content:
            raise HTTPException(status_code=404, detail="content not found")
        content.status = ReviewStatus.REJECTED
        content.reviewed_at = datetime.now(UTC)
        content.review_note = request.reason
        container.memory.update_content(content)
        # Record experience
        container.memory.append_memory_record(
            __import__("backend.app.domain.models", fromlist=["MemoryRecord"]).MemoryRecord(
                namespace="viking://agent/experience",
                kind="experience",
                payload={
                    "action": "reject",
                    "result": "success",
                    "content_ids": [content_id],
                    "errors": [request.reason],
                },
                source="API.reject",
            )
        )
        return content.model_dump(mode="json")

    @api.post("/publish/{platform}/{content_id}")
    async def publish(platform: str, content_id: str) -> dict:
        content = container.memory.get_content(content_id)
        if not content:
            raise HTTPException(status_code=404, detail="content not found")
        if (
            container.config.review.require_human_approval
            and content.status != ReviewStatus.APPROVED
        ):
            raise HTTPException(status_code=409, detail="content requires human approval")
        if content.platform != platform:
            raise HTTPException(status_code=409, detail="content platform mismatch")
        result = await container.publishing_agent.publish_content(content)
        if not result:
            refreshed = container.memory.get_content(content_id)
            errors = container.publishing_agent.validate_content(content)
            metadata = refreshed.metadata if refreshed else {}
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "content was not publishable",
                    "errors": metadata.get("publish_validation_errors", errors),
                    "last_publish_error": metadata.get("last_publish_error"),
                },
            )
        return result

    @api.get("/publishers/{platform}/check")
    async def check_publisher(platform: str) -> dict:
        try:
            publisher = container.publishers.get(platform)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="publisher not found") from error
        return await publisher.check()

    @api.get("/publishers/checks")
    async def check_publishers() -> list[dict]:
        results = []
        for platform in container.publishers.names():
            publisher = container.publishers.get(platform)
            results.append(await publisher.check())
        return results

    @api.get("/publish/{platform}/{content_id}/validate")
    async def validate_publish(platform: str, content_id: str) -> dict:
        content = container.memory.get_content(content_id)
        if not content:
            raise HTTPException(status_code=404, detail="content not found")
        if content.platform != platform:
            raise HTTPException(status_code=409, detail="content platform mismatch")
        errors = container.publishing_agent.validate_content(content)
        return {"ok": not errors, "errors": errors}

    @api.get("/skills/proposals")
    async def skill_proposals(status: ReviewStatus | None = STATUS_QUERY) -> list[dict]:
        return [
            proposal.model_dump(mode="json")
            for proposal in container.memory.list_skill_proposals(status=status)
        ]

    @api.post("/skills/proposals")
    async def create_skill_proposal(request: SkillProposalRequest) -> dict:
        proposal = container.skill_evolution_agent.propose(
            title=request.title,
            reason=request.reason,
            proposed_skill_name=request.proposed_skill_name,
            draft_prompt=request.draft_prompt,
            content_types=request.content_types,
            platforms=request.platforms,
        )
        return proposal.model_dump(mode="json")

    @api.post("/skills/proposals/discover")
    async def discover_skill_proposals() -> list[dict]:
        return [
            proposal.model_dump(mode="json")
            for proposal in container.skill_evolution_agent.discover_proposals()
        ]

    @api.post("/skills/proposals/{proposal_id}/approve")
    async def approve_skill_proposal(proposal_id: str, request: ApprovalRequest) -> dict:
        proposal = container.skill_evolution_agent.approve(proposal_id, request.note)
        if not proposal:
            raise HTTPException(status_code=404, detail="skill proposal not found")
        return proposal.model_dump(mode="json")

    @api.post("/skills/proposals/{proposal_id}/reject")
    async def reject_skill_proposal(proposal_id: str, request: RejectRequest) -> dict:
        proposal = container.skill_evolution_agent.reject(proposal_id, request.reason)
        if not proposal:
            raise HTTPException(status_code=404, detail="skill proposal not found")
        return proposal.model_dump(mode="json")

    return api