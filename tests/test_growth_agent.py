from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.growth_agent import GrowthAgent
from backend.app.domain.models import AgentMetric, MemoryRecord
from backend.app.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_growth_agent_import_metrics(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = GrowthAgent(memory)

    metrics = [
        AgentMetric(metric_name="page_views", value=1500.0, dimensions={"platform": "blog"}),
        AgentMetric(metric_name="engagement", value=0.75, dimensions={"platform": "x"}),
    ]

    count = await agent.import_metrics(metrics)
    assert count == 2

    # Verify metrics are stored
    stored = memory.search_namespace(namespace="viking://agent/metrics", kind="metric")
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_growth_agent_analyze_from_failures(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = GrowthAgent(memory)

    # Add repeated failure experiences
    for i in range(3):
        memory.append_memory_record(
            MemoryRecord(
                namespace="viking://agent/experience",
                kind="experience",
                payload={
                    "action": "publish",
                    "result": "failure",
                    "errors": [f"Error {i}"],
                },
                source="test",
            )
        )

    signals = await agent.analyze()

    # Should detect the repeated failures
    failure_signals = [s for s in signals if "failed" in s.observation.lower()]
    assert len(failure_signals) >= 1
    assert all(s.recommendation for s in signals)


@pytest.mark.asyncio
async def test_growth_agent_evidence_ids_match_failed_action(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = GrowthAgent(memory)

    publish_ids = []
    for i in range(2):
        record = MemoryRecord(
            namespace="viking://agent/experience",
            kind="experience",
            payload={"action": "publish", "result": "failure", "errors": [f"p{i}"]},
            source="test",
        )
        publish_ids.append(record.id)
        memory.append_memory_record(record)
    generate_record = MemoryRecord(
        namespace="viking://agent/experience",
        kind="experience",
        payload={"action": "generate", "result": "failure", "errors": ["g0"]},
        source="test",
    )
    memory.append_memory_record(generate_record)

    signals = await agent.analyze()

    publish_signal = next(
        signal for signal in signals if "Action 'publish'" in signal.observation
    )
    assert set(publish_signal.evidence_ids) == set(publish_ids)
    assert generate_record.id not in publish_signal.evidence_ids


@pytest.mark.asyncio
async def test_growth_agent_analyze_empty_no_signals(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")
    agent = GrowthAgent(memory)

    signals = await agent.analyze()
    assert signals == []
