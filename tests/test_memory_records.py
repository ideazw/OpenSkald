from __future__ import annotations

from pathlib import Path

from backend.app.domain.models import MemoryRecord
from backend.app.memory.store import MemoryStore


def test_append_and_search_namespace(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")

    # Append records in different namespaces
    r1 = MemoryRecord(
        namespace="viking://agent/experience", kind="experience",
        payload={"action": "test"},
    )
    r2 = MemoryRecord(
        namespace="viking://agent/reflections", kind="reflection",
        payload={"lesson": "test"},
    )
    r3 = MemoryRecord(
        namespace="viking://project/articles", kind="note",
        payload={"note": "test"},
    )

    memory.append_memory_record(r1)
    memory.append_memory_record(r2)
    memory.append_memory_record(r3)

    # Search by namespace prefix
    agent_records = memory.search_namespace(namespace="viking://agent/")
    assert len(agent_records) == 2

    # Search by kind
    experience_records = memory.search_namespace(namespace="viking://agent/", kind="experience")
    assert len(experience_records) == 1
    assert experience_records[0].kind == "experience"

    # Search non-matching namespace
    empty = memory.search_namespace(namespace="viking://nonexistent/")
    assert empty == []


def test_list_reflections(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")

    # Add mixed records
    memory.append_memory_record(
        MemoryRecord(
        namespace="viking://agent/reflections", kind="reflection",
        payload={"lesson": "ref1"},
    )
    )
    memory.append_memory_record(
        MemoryRecord(
        namespace="viking://agent/reflections", kind="reflection",
        payload={"lesson": "ref2"},
    )
    )
    memory.append_memory_record(
        MemoryRecord(
        namespace="viking://agent/experience", kind="experience",
        payload={"action": "gen"},
    )
    )

    reflections = memory.list_reflections()
    assert len(reflections) == 2
    assert all(r.kind == "reflection" for r in reflections)


def test_list_experiences(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")

    memory.append_memory_record(
        MemoryRecord(
        namespace="viking://agent/experience", kind="experience",
        payload={"action": "generate"},
    )
    )
    memory.append_memory_record(
        MemoryRecord(
        namespace="viking://agent/experience", kind="experience",
        payload={"action": "publish"},
    )
    )
    memory.append_memory_record(
        MemoryRecord(
        namespace="viking://agent/reflections", kind="reflection",
        payload={"lesson": "l1"},
    )
    )

    experiences = memory.list_experiences()
    assert len(experiences) == 2
    assert all(e.kind == "experience" for e in experiences)


def test_search_namespace_respects_limit(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")

    for i in range(5):
        memory.append_memory_record(
            MemoryRecord(
            namespace="viking://agent/experience", kind="experience",
            payload={"index": i},
        )
        )

    all_records = memory.search_namespace(namespace="viking://agent/experience", limit=10)
    assert len(all_records) == 5

    limited = memory.search_namespace(namespace="viking://agent/experience", limit=2)
    assert len(limited) == 2


def test_memory_record_default_fields() -> None:
    record = MemoryRecord(namespace="viking://test", kind="note", payload={"key": "value"})
    assert record.id is not None
    assert record.source is None
    assert record.confidence == 1.0
    assert record.created_at is not None
