from pathlib import Path

import pytest

from backend.app.config.settings import config_summary, load_config, validate_config
from backend.app.domain.models import ContentType


def test_load_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
llm:
  provider: deepseek
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY
  model: test-model
publishers:
  x:
    enabled: false
    dry_run: true
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.llm.model == "test-model"
    assert config.publishers["x"].dry_run is True


def test_load_config_raises_for_explicit_missing_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config(missing_path)


def test_load_config_raises_for_missing_env_path(tmp_path: Path, monkeypatch) -> None:
    missing_path = tmp_path / "missing-env.yaml"
    monkeypatch.setenv("OPENVIKING_AGENT_CONFIG", str(missing_path))

    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config()


def test_config_summary_redacts_secret_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REAL_API_KEY", "super-secret-value")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: test
llm:
  api_key_env: REAL_API_KEY
  model: test-model
openviking:
  knowledge_base_path: {tmp_path}
publishers:
  x:
    account_id: account-123
    credentials_env: X_SECRET
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    summary = config_summary(config)

    assert summary["llm"]["api_key_configured"] is True
    assert "super-secret-value" not in str(summary)
    assert summary["publishers"]["x"]["account_id_configured"] is True


def test_validate_config_flags_production_without_human_approval(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: production
llm:
  api_key_env: MISSING_KEY
  model: prod-model
openviking:
  knowledge_base_path: {tmp_path}
review:
  require_human_approval: false
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    issues = validate_config(config)

    assert any(issue.level == "error" for issue in issues)
    assert any("human approval" in issue.message for issue in issues)


def test_validate_config_rejects_current_directory_knowledge_path() -> None:
    config = load_config("config/config.yaml")
    config.openviking.knowledge_base_path = Path(".")

    issues = validate_config(config)

    assert any(
        issue.level == "error"
        and "cannot be empty or point to the current directory" in issue.message
        for issue in issues
    )


def test_validate_config_requires_enabled_publisher_credentials(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: production
llm:
  api_key_env: MISSING_KEY
  model: prod-model
openviking:
  knowledge_base_path: {tmp_path}
publishers:
  x:
    enabled: true
    dry_run: false
    credentials_env: X_MISSING_CREDS
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    issues = validate_config(config)

    assert any("publisher x" in issue.message.lower() for issue in issues)


def test_validate_config_requires_publisher_credential_keys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROD_LLM_KEY", "secret")
    monkeypatch.setenv("X_CREDS", '{"bearer_token":"app_only"}')
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: production
llm:
  api_key_env: PROD_LLM_KEY
  model: prod-model
openviking:
  knowledge_base_path: {tmp_path}
publishers:
  x:
    enabled: true
    dry_run: false
    credentials_env: X_CREDS
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    issues = validate_config(config)

    assert any(
        "missing keys: consumer_key, consumer_secret, access_token, access_token_secret"
        in issue.message
        for issue in issues
    )


def test_validate_config_accepts_x_oauth1_api_key_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROD_LLM_KEY", "secret")
    monkeypatch.setenv(
        "X_CREDS",
        (
            '{"api_key":"consumer","api_key_secret":"consumer_secret",'
            '"access_token":"access","access_token_secret":"access_secret"}'
        ),
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: production
llm:
  api_key_env: PROD_LLM_KEY
  model: prod-model
openviking:
  knowledge_base_path: {tmp_path}
publishers:
  x:
    enabled: true
    dry_run: false
    credentials_env: X_CREDS
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    issues = validate_config(config)

    assert issues == []


def test_validate_config_rejects_invalid_publisher_credentials_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROD_LLM_KEY", "secret")
    monkeypatch.setenv("WECHAT_CREDS", "not-json")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: production
llm:
  api_key_env: PROD_LLM_KEY
  model: prod-model
openviking:
  knowledge_base_path: {tmp_path}
publishers:
  wechat:
    enabled: true
    dry_run: false
    credentials_env: WECHAT_CREDS
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    issues = validate_config(config)

    assert any("not valid JSON" in issue.message for issue in issues)


def test_validate_config_allows_production_blog_output_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PROD_LLM_KEY", "secret")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: production
llm:
  api_key_env: PROD_LLM_KEY
  model: prod-model
openviking:
  knowledge_base_path: {tmp_path}
publishers:
  blog:
    enabled: true
    dry_run: false
    account_id: {tmp_path / "blog"}
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    issues = validate_config(config)

    assert not [issue for issue in issues if issue.level == "error"]


def test_default_config_schedules_all_required_content_types() -> None:
    config = load_config("config/config.yaml")
    scheduled_content_types = {
        job.content_type
        for job in config.scheduler.values()
        if job.enabled and job.action == "generate"
    }

    assert scheduled_content_types >= {
        ContentType.DAILY_SUMMARY.value,
        ContentType.WEEKLY_SUMMARY.value,
        ContentType.HOT_TOPIC_ANALYSIS.value,
        ContentType.DEEP_TECHNICAL_ANALYSIS.value,
    }
