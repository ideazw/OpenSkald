from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.domain.models import MemoryRecord
from backend.app.memory.backend import JsonlMemoryBackend, OpenVikingMemoryBackend


def test_openviking_backend_raises_when_local_fallback_fails(tmp_path: Path) -> None:
    class FailingJsonlBackend(JsonlMemoryBackend):
        def __init__(self, path: Path) -> None:
            super().__init__(path)
            self.append_calls = 0

        def append(self, record: MemoryRecord) -> None:
            self.append_calls += 1
            raise OSError("disk unavailable")

    fallback = FailingJsonlBackend(tmp_path / "memory_records.jsonl")
    backend = OpenVikingMemoryBackend(
        endpoint="http://openviking.local",
        workspace_id="open-skald",
        local_fallback=fallback,
    )

    with pytest.raises(OSError, match="disk unavailable"):
        backend.append(MemoryRecord(namespace="viking://agent/test", kind="note"))

    assert fallback.append_calls == 1
    assert backend.health()["degraded"] is True
