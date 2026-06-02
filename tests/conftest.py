from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.llm.provider import LLMProvider
from backend.app.memory.store import MemoryStore
from backend.app.skills.base import SkillRegistry


class FakeLLMProvider(LLMProvider):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        return f"generated from {len(system_prompt)} chars: {user_prompt[:30]}"


@pytest.fixture
def tmp_memory(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skill_proposals.jsonl")


@pytest.fixture
def tmp_knowledge(tmp_path: Path) -> Path:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "demo.md").write_text(
        "---\ntitle: Demo Article\ntags:\n  - agents\n---\n# Demo\nAgent content.\n",
        encoding="utf-8",
    )
    return knowledge


@pytest.fixture
def tmp_config_path(tmp_path: Path, tmp_knowledge: Path, tmp_memory: MemoryStore) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: test
log_level: INFO
llm:
  provider: demo
  model: demo-local-deterministic
openviking:
  knowledge_base_path: {tmp_knowledge}
publishers:
  blog:
    enabled: true
    account_id: {tmp_memory.memory.path.parent / "blog"}
    dry_run: false
  x:
    enabled: false
    dry_run: true
  wechat:
    enabled: false
    dry_run: true
  xiaohongshu:
    enabled: false
    dry_run: true
scheduler: {{}}
memory:
  storage_path: {tmp_memory.memory.path}
  skill_proposals_path: {tmp_memory.skill_proposals.path}
""",
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def skill_registry() -> SkillRegistry:
    registry = SkillRegistry(Path("backend/app/skills"))
    registry.load()
    return registry
