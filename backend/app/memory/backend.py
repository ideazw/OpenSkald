from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backend.app.domain.models import MemoryRecord


class MemoryBackend(ABC):
    """Abstract backend for namespace-addressable memory storage.

    Primary implementation uses local JSONL files.
    Future implementations can use OpenViking remote storage.
    """

    @abstractmethod
    def append(self, record: MemoryRecord) -> None:
        ...

    @abstractmethod
    def search(
        self, namespace: str, kind: str | None = None, limit: int = 20
    ) -> list[MemoryRecord]:
        ...

    @abstractmethod
    def health(self) -> dict:
        """Return backend health status.

        Returns:
            dict with "ok": bool, optional "degraded": bool, and details.
        """
        ...


class JsonlMemoryBackend(MemoryBackend):
    """Local JSONL-backed memory storage (default implementation)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: MemoryRecord) -> None:
        import json

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def search(
        self, namespace: str, kind: str | None = None, limit: int = 20
    ) -> list[MemoryRecord]:
        import json

        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        if kind:
            raw = [
                r for r in records
                if r.get("namespace", "").startswith(namespace) and r.get("kind") == kind
            ]
        else:
            raw = [r for r in records if r.get("namespace", "").startswith(namespace)]
        raw.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return [MemoryRecord.model_validate(r) for r in raw[:limit]]

    def health(self) -> dict:
        return {
            "ok": True,
            "backend": "jsonl",
            "path": str(self.path),
            "exists": self.path.exists(),
        }


class OpenVikingMemoryBackend(MemoryBackend):
    """Remote OpenViking workspace memory backend.

    NOTE: This is an interface placeholder. The actual remote protocol
    will be implemented in Phase E. For now, it provides the contract
    and falls back to local JSONL on write failure.
    """

    def __init__(
        self,
        endpoint: str,
        workspace_id: str,
        local_fallback: JsonlMemoryBackend,
    ) -> None:
        self.endpoint = endpoint
        self.workspace_id = workspace_id
        self.local_fallback = local_fallback
        self._degraded = False

    def append(self, record: MemoryRecord) -> None:
        try:
            # Future: send to OpenViking workspace
            # For now, always fallback to local
            self.local_fallback.append(record)
        except Exception:
            self._degraded = True
            raise

    def search(
        self, namespace: str, kind: str | None = None, limit: int = 20
    ) -> list[MemoryRecord]:
        return self.local_fallback.search(namespace, kind, limit)

    def health(self) -> dict:
        return {
            "ok": True,
            "backend": "openviking",
            "endpoint": self.endpoint,
            "workspace_id": self.workspace_id,
            "degraded": self._degraded,
        }
