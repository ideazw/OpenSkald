from pathlib import Path

from backend.app.domain.models import ContentType
from backend.app.skills.base import SkillRegistry


def test_skill_registry_loads_declarative_skills() -> None:
    registry = SkillRegistry(Path("backend/app/skills"))
    registry.load()

    assert "x_writer" in registry.names()
    assert registry.for_content(ContentType.DAILY_SUMMARY, "x")[0].metadata.name == "x_writer"
