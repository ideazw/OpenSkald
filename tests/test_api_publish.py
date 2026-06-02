from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config.settings import PublisherConfig
from backend.app.domain.models import ContentType, GeneratedContent, ReviewStatus
from backend.app.main import create_app
from tests.test_publishing_agent import FailingPublisher


def _write_config(tmp_path: Path) -> Path:
    knowledge_path = tmp_path / "knowledge"
    knowledge_path.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: test
log_level: INFO
llm:
  provider: demo
  model: demo-local-deterministic
openviking:
  knowledge_base_path: {knowledge_path}
publishers:
  x:
    enabled: true
    dry_run: true
scheduler: {{}}
memory:
  storage_path: {tmp_path / "memory.jsonl"}
  skill_proposals_path: {tmp_path / "skill_proposals.jsonl"}
  article_index_path: {tmp_path / "articles.jsonl"}
""",
        encoding="utf-8",
    )
    return config_path


def test_api_publish_only_publishes_requested_content(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))
    container = app.state.container
    target = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Target",
        body="1/ Target",
        status=ReviewStatus.APPROVED,
    )
    other = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Other",
        body="1/ Other",
        status=ReviewStatus.APPROVED,
    )
    container.memory.remember_content(target)
    container.memory.remember_content(other)

    with TestClient(app) as client:
        response = client.post(f"/api/publish/x/{target.id}")

    assert response.status_code == 200
    assert response.json()["content_id"] == target.id
    assert container.memory.get_content(target.id).status == ReviewStatus.PUBLISHED
    assert container.memory.get_content(other.id).status == ReviewStatus.APPROVED


def test_api_publisher_check_for_dry_run_platform(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))

    with TestClient(app) as client:
        response = client.get("/api/publishers/x/check")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["dry_run"] is True


def test_api_publisher_check_all(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))

    with TestClient(app) as client:
        response = client.get("/api/publishers/checks")

    assert response.status_code == 200
    assert response.json()[0]["platform"] == "x"
    assert response.json()[0]["ok"] is True


def test_api_generate_fails_without_articles(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))

    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={"content_type": "daily_summary", "platforms": ["x"]},
        )

    assert response.status_code == 409
    assert "No OpenViking articles" in response.json()["detail"]


def test_api_content_summary_and_failures(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))
    container = app.state.container
    failed = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Failed",
        body="1/ Failed",
        status=ReviewStatus.APPROVED,
        metadata={"last_publish_error": {"type": "RuntimeError", "message": "no token"}},
    )
    container.memory.remember_content(failed)

    with TestClient(app) as client:
        summary = client.get("/api/content/summary")
        failures = client.get("/api/content/failures")

    assert summary.status_code == 200
    assert summary.json()["failed"] == 1
    assert failures.status_code == 200
    assert failures.json()[0]["id"] == failed.id


def test_api_memory_timeline_and_search(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))
    container = app.state.container
    item = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="RAG Thread",
        body="Retrieval quality matters.",
    )
    container.memory.remember_content(item)

    with TestClient(app) as client:
        timeline = client.get("/api/memory/timeline?platform=x")
        search = client.get("/api/memory/search?q=retrieval")

    assert timeline.status_code == 200
    assert timeline.json()[0]["id"] == item.id
    assert search.status_code == 200
    assert search.json()[0]["id"] == item.id


def test_api_knowledge_ingest_and_search(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    knowledge_file = tmp_path / "knowledge" / "openviking.md"
    knowledge_file.write_text(
        """---
title: OpenViking Memory
tags:
  - memory
---
# OpenViking Memory

Local notes can feed publishing automation.
""",
        encoding="utf-8",
    )
    app = create_app(str(config_path))

    with TestClient(app) as client:
        ingest = client.post("/api/knowledge/ingest")
        articles = client.get("/api/knowledge/search?q=publishing")

    assert ingest.status_code == 200
    assert ingest.json()["ingested"] == 1
    assert articles.status_code == 200
    assert articles.json()[0]["title"] == "OpenViking Memory"


def test_api_skill_discovery_from_memory(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))
    container = app.state.container
    for index in range(2):
        container.memory.remember_content(
            GeneratedContent(
                content_type=ContentType.DAILY_SUMMARY,
                platform="x",
                title=f"Too long {index}",
                body="x" * 281,
                status=ReviewStatus.APPROVED,
                metadata={
                    "publish_validation_errors": [
                        "x posts exceed 280 characters at positions: [1]"
                    ]
                },
            )
        )

    with TestClient(app) as client:
        response = client.post("/api/skills/proposals/discover")

    assert response.status_code == 200
    assert response.json()[0]["proposed_skill_name"] == "x_thread_compressor"


def test_api_publish_returns_persisted_publish_error(tmp_path: Path) -> None:
    app = create_app(str(_write_config(tmp_path)))
    container = app.state.container
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Target",
        body="1/ Target",
        status=ReviewStatus.APPROVED,
    )
    container.memory.remember_content(content)
    failing = FailingPublisher(PublisherConfig(enabled=True, dry_run=False))
    failing.platform = "x"
    container.publishers._publishers["x"] = failing

    with TestClient(app) as client:
        response = client.post(f"/api/publish/x/{content.id}")

    stored = container.memory.get_content(content.id)
    assert response.status_code == 409
    assert response.json()["detail"]["last_publish_error"]["type"] == "RuntimeError"
    assert stored.status == ReviewStatus.APPROVED
