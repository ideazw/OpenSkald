from __future__ import annotations

from pathlib import Path

from backend.app.config.settings import load_config


def test_agent_llm_defaults_to_global(tmp_path: Path) -> None:
    """When no per-agent LLM is configured, all agents use the global LLM config."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""
llm:
  provider: deepseek
  model: deepseek-v4-flash
memory:
  storage_path: memory.jsonl
  skill_proposals_path: proposals.jsonl
""", encoding="utf-8")

    config = load_config(str(config_path))
    assert config.llm.model == "deepseek-v4-flash"
    assert config.agent_llm.content.model_dump(exclude_none=True) == {}
    assert config.agent_llm.reflection.model_dump(exclude_none=True) == {}
    assert config.agent_llm.writing.model_dump(exclude_none=True) == {}


def test_agent_llm_per_agent_override(tmp_path: Path) -> None:
    """Per-agent LLM config overrides only specified fields; rest fall back to global."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""
llm:
  provider: deepseek
  model: deepseek-v4-flash
  base_url: https://api.deepseek.com

agent_llm:
  reflection:
    model: gpt-4o
    provider: openai
  writing:
    model: o3-mini

memory:
  storage_path: memory.jsonl
  skill_proposals_path: proposals.jsonl
""", encoding="utf-8")

    config = load_config(str(config_path))

    # Global stays unchanged
    assert config.llm.model == "deepseek-v4-flash"

    # Reflection overrides model + provider
    assert config.agent_llm.reflection.model == "gpt-4o"
    assert config.agent_llm.reflection.provider == "openai"

    # Writing overrides model only
    assert config.agent_llm.writing.model == "o3-mini"
    assert config.agent_llm.writing.provider is None  # falls back to global

    # Content uses all defaults
    assert config.agent_llm.content.model_dump(exclude_none=True) == {}


def test_agent_llm_config_summary(tmp_path: Path) -> None:
    """Config summary should expose per-agent LLM overrides."""
    from backend.app.config.settings import config_summary

    config_path = tmp_path / "config.yaml"
    config_path.write_text("""
llm:
  provider: deepseek
  model: deepseek-v4-flash

agent_llm:
  reflection:
    model: gpt-4o

memory:
  storage_path: memory.jsonl
  skill_proposals_path: proposals.jsonl
""", encoding="utf-8")

    config = load_config(str(config_path))
    summary = config_summary(config)

    assert "agent_llm" in summary
    assert summary["agent_llm"]["content"] is None  # no override
    assert summary["agent_llm"]["reflection"] == {"model": "gpt-4o"}
    assert summary["agent_llm"]["writing"] is None
