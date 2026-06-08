from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from backend.app.agents.content_agent import ContentAgent
from backend.app.agents.growth_agent import GrowthAgent
from backend.app.agents.publishing_agent import PublishingAgent
from backend.app.agents.reflection_agent import ReflectionAgent
from backend.app.agents.skill_evolution_agent import SkillEvolutionAgent
from backend.app.domain.models import (
    AgentMode,
    AgentResult,
    AgentRun,
    AgentRunStatus,
    ContentType,
    MemoryRecord,
)
from backend.app.memory.store import MemoryStore


class OpenSkaldAgentRuntime:
    """Unified runtime that wraps all agents with execution tracking."""

    def __init__(
        self,
        content_agent: ContentAgent,
        publishing_agent: PublishingAgent,
        reflection_agent: ReflectionAgent,
        growth_agent: GrowthAgent,
        skill_evolution_agent: SkillEvolutionAgent,
        memory: MemoryStore,
        writing_llm: Any | None = None,
    ) -> None:
        self.content_agent = content_agent
        self.publishing_agent = publishing_agent
        self.reflection_agent = reflection_agent
        self.growth_agent = growth_agent
        self.skill_evolution_agent = skill_evolution_agent
        self.memory = memory
        self.writing_llm = writing_llm or content_agent.llm

    async def run(
        self,
        objective: str,
        content_type: ContentType,
        platforms: list[str],
        mode: AgentMode = AgentMode.SINGLE,
    ) -> AgentRun:
        """Execute an agent run with the given mode and record the full trace."""
        run = AgentRun(
            input=objective,
            mode=mode,
            status=AgentRunStatus.RUNNING,
        )
        self._store_agent_run(run)
        errors: list[str] = []
        artifacts: list[dict[str, Any]] = []
        memory_writes = 0
        start = time.monotonic()

        try:
            if mode == AgentMode.SINGLE:
                result = await self._run_single(content_type, platforms)
            else:
                from backend.app.agents.orchestrator import MultiAgentOrchestrator
                from backend.app.agents.research_agent import ResearchAgent
                from backend.app.agents.review_agent import ReviewAgent
                from backend.app.agents.writing_agent import WritingAgent

                orchestrator = MultiAgentOrchestrator(
                    research_agent=ResearchAgent(
                        self.content_agent.knowledge_base,
                        self.memory,
                    ),
                    writing_agent=WritingAgent(
                        self.content_agent.skills,
                        self.writing_llm,
                    ),
                    review_agent=ReviewAgent(self.memory),
                    publishing_agent=self.publishing_agent,
                    reflection_agent=self.reflection_agent,
                    growth_agent=self.growth_agent,
                    memory=self.memory,
                )
                result = await orchestrator.run(
                    objective=objective,
                    content_type=content_type,
                    platforms=platforms,
                )

            errors = result.errors
            artifacts = result.artifacts
            for mw in result.memory_writes:
                self.memory.append_memory_record(mw)
                memory_writes += 1

        except Exception as exc:
            errors.append(f"Runtime error: {exc}")
            run.status = AgentRunStatus.FAILED

        run.latency_ms = int((time.monotonic() - start) * 1000)

        if run.status != AgentRunStatus.FAILED:
            if errors:
                run.status = AgentRunStatus.PARTIAL
            else:
                run.status = AgentRunStatus.COMPLETED

        run.output = f"Generated {len([a for a in artifacts if a.get('type') != 'error'])} item(s)"
        if errors:
            run.output += f" with {len(errors)} error(s)"
        run.artifacts = artifacts
        run.memory_writes = memory_writes
        run.errors = errors
        run.completed_at = datetime.now(UTC)
        self._update_agent_run(run)

        # Record runtime experience
        self.memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/experience",
                kind="experience",
                payload={
                    "action": "agent_run",
                    "result": (
                        "failure"
                        if run.status == AgentRunStatus.FAILED
                        else "partial" if errors else "success"
                    ),
                    "mode": mode.value,
                    "content_type": content_type.value,
                    "platforms": platforms,
                    "artifacts_count": len(artifacts),
                    "errors": errors,
                    "latency_ms": run.latency_ms,
                },
                source="OpenSkaldAgentRuntime",
            )
        )

        return run

    async def _run_single(
        self, content_type: ContentType, platforms: list[str]
    ) -> AgentResult:
        """Run in single mode: generate, then optionally reflect."""
        generated = await self.content_agent.generate(content_type, platforms)
        artifacts = []
        for item in generated:
            artifacts.append(item.model_dump(mode="json"))

        # Discover reflections after generation
        reflections = await self.reflection_agent.discover()
        memory_writes: list[MemoryRecord] = []
        for ref in reflections:
            memory_writes.append(
                MemoryRecord(
                    namespace="viking://agent/reflections",
                    kind="reflection",
                    payload=ref.model_dump(mode="json"),
                    source="OpenSkaldAgentRuntime.auto_reflect",
                    confidence=ref.confidence,
                )
            )

        return AgentResult(artifacts=artifacts, memory_writes=memory_writes)

    def _store_agent_run(self, run: AgentRun) -> None:
        import json
        records_path = self.memory.memory.path.parent / "memory_records.jsonl"
        records_path.parent.mkdir(parents=True, exist_ok=True)
        with records_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(run.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def _update_agent_run(self, run: AgentRun) -> None:
        import json
        records_path = self.memory.memory.path.parent / "memory_records.jsonl"
        records_path.parent.mkdir(parents=True, exist_ok=True)
        with records_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(run.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def get_run(self, run_id: str) -> dict | None:
        """Retrieve a stored agent run."""
        records_path = self.memory.memory.path.parent / "memory_records.jsonl"
        if not records_path.exists():
            return None
        latest_run = None
        with records_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = __import__("json").loads(line)
                    if row.get("id") == run_id and "latency_ms" in row:
                        latest_run = row
        return latest_run

    def list_runs(self, limit: int = 20) -> list[dict]:
        """List recent agent runs."""
        records_path = self.memory.memory.path.parent / "memory_records.jsonl"
        if not records_path.exists():
            return []
        runs_dict = {}
        with records_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = __import__("json").loads(line)
                    if "latency_ms" in row:
                        runs_dict[row["id"]] = row
        runs = list(runs_dict.values())
        runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return runs[:limit]
