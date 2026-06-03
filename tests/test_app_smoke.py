from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_app_boots_and_exposes_health_and_redacted_config(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    config_path = tmp_path / "config.yaml"
    memory_path = tmp_path / "memory.jsonl"
    proposals_path = tmp_path / "skill_proposals.jsonl"
    articles_path = tmp_path / "articles.jsonl"
    config_path.write_text(
        f"""
environment: test
log_level: INFO
llm:
  provider: deepseek
  base_url: https://api.deepseek.com
  api_key_env: TEST_SECRET_KEY
  model: smoke-model
openviking:
  knowledge_base_path: {knowledge_path}
publishers:
  x:
    enabled: false
    dry_run: true
scheduler: {{}}
memory:
  storage_path: {memory_path}
  skill_proposals_path: {proposals_path}
  article_index_path: {articles_path}
""",
        encoding="utf-8",
    )

    app = create_app(str(config_path))
    with TestClient(app) as client:
        health = client.get("/api/health")
        summary = client.get("/api/config/summary")
        status = client.get("/api/status")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert summary.status_code == 200
    assert summary.json()["llm"]["api_key_env"] == "TEST_SECRET_KEY"
    assert "super-secret-value" not in str(summary.json())
    assert status.status_code == 200
    assert status.json()["ok"] is True
    assert status.json()["knowledge"]["indexed_articles"] == 0
    assert status.json()["publishers"]["x"]["dry_run"] is True
