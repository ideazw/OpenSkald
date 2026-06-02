from pathlib import Path

from backend.app import cli
from backend.app.domain.models import ReviewStatus


def _write_config(tmp_path: Path, knowledge_path: Path | None = None) -> Path:
    knowledge = knowledge_path or tmp_path / "knowledge"
    knowledge.mkdir(exist_ok=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
environment: test
log_level: INFO
llm:
  provider: cc_switch
  base_url: http://localhost:3456/v1
  api_key_env: TEST_KEY
  model: test-model
openviking:
  knowledge_base_path: {knowledge}
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


def test_cli_validate_config_success(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = cli.main(["--config", str(config_path), "validate-config"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"ok": true' in output


def test_cli_config_summary_outputs_redacted_json(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("TEST_KEY", "secret-value")
    config_path = _write_config(tmp_path)

    exit_code = cli.main(["--config", str(config_path), "config-summary"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"api_key_configured": true' in output
    assert "secret-value" not in output


def test_cli_status_outputs_operational_summary(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = cli.main(["--config", str(config_path), "status"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"knowledge"' in output
    assert '"publishers"' in output
    assert '"indexed_articles": 0' in output


def test_cli_generate_once_fails_without_articles(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = cli.main(
        [
            "--config",
            str(config_path),
            "generate-once",
            "--content-type",
            "daily_summary",
            "--platform",
            "x",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "No OpenViking articles" in output


def test_cli_review_list_reads_memory(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    container = cli.build_container(str(config_path))
    generated = container.generated_content_from_record(
        {
            "content_type": "daily_summary",
            "platform": "x",
            "title": "Review me",
            "body": "1/ Ready",
        }
    )
    container.memory.remember_content(generated)

    exit_code = cli.main(["--config", str(config_path), "review-list", "--platform", "x"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Review me" in output


def test_cli_content_summary_and_failures(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    container = cli.build_container(str(config_path))
    failed = container.generated_content_from_record(
        {
            "content_type": "daily_summary",
            "platform": "x",
            "title": "Failed",
            "body": "1/ Failed",
            "status": "approved",
            "metadata": {
                "last_publish_error": {"type": "RuntimeError", "message": "no token"}
            },
        }
    )
    container.memory.remember_content(failed)

    summary_code = cli.main(["--config", str(config_path), "content-summary"])
    failures_code = cli.main(["--config", str(config_path), "content-failures"])

    output = capsys.readouterr().out
    assert summary_code == 0
    assert failures_code == 0
    assert '"failed": 1' in output
    assert "no token" in output


def test_cli_memory_timeline_and_search(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    container = cli.build_container(str(config_path))
    item = container.generated_content_from_record(
        {
            "content_type": "daily_summary",
            "platform": "x",
            "title": "RAG Thread",
            "body": "Retrieval quality matters.",
        }
    )
    container.memory.remember_content(item)

    timeline_code = cli.main(
        ["--config", str(config_path), "memory-timeline", "--platform", "x"]
    )
    search_code = cli.main(
        ["--config", str(config_path), "memory-search", "--query", "retrieval"]
    )

    output = capsys.readouterr().out
    assert timeline_code == 0
    assert search_code == 0
    assert "RAG Thread" in output
    assert "Retrieval quality matters" in output


def test_cli_knowledge_ingest_and_list(tmp_path: Path, capsys) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "rag.md").write_text(
        """---
title: RAG Operations
tags:
  - rag
---
# RAG Operations

Production retrieval needs memory and review.
""",
        encoding="utf-8",
    )
    config_path = _write_config(tmp_path, knowledge)

    ingest_code = cli.main(["--config", str(config_path), "knowledge-ingest"])
    list_code = cli.main(
        ["--config", str(config_path), "knowledge-list", "--query", "retrieval"]
    )

    output = capsys.readouterr().out
    assert ingest_code == 0
    assert list_code == 0
    assert '"ingested": 1' in output
    assert "RAG Operations" in output


def test_cli_skills_discover(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    container = cli.build_container(str(config_path))
    for index in range(2):
        item = container.generated_content_from_record(
            {
                "content_type": "daily_summary",
                "platform": "x",
                "title": f"Too long {index}",
                "body": "x" * 281,
                "status": "approved",
                "metadata": {
                    "publish_validation_errors": [
                        "x posts exceed 280 characters at positions: [1]"
                    ]
                },
            }
        )
        container.memory.remember_content(item)

    exit_code = cli.main(["--config", str(config_path), "skills-discover"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "x_thread_compressor" in output


def test_cli_review_approve_and_publish_content(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    container = cli.build_container(str(config_path))
    generated = container.generated_content_from_record(
        {
            "content_type": "daily_summary",
            "platform": "x",
            "title": "Approve me",
            "body": "1/ Ready",
        }
    )
    container.memory.remember_content(generated)

    approve_code = cli.main(
        ["--config", str(config_path), "review-approve", "--content-id", generated.id]
    )
    publish_code = cli.main(
        ["--config", str(config_path), "publish-content", "--content-id", generated.id]
    )

    output = capsys.readouterr().out
    assert approve_code == 0
    assert publish_code == 0
    assert '"status": "approved"' in output
    assert '"dry_run": true' in output


def test_cli_publisher_check_dry_run(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = cli.main(["--config", str(config_path), "publisher-check", "--platform", "x"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"platform": "x"' in output
    assert "dry-run mode" in output


def test_cli_publisher_check_all(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = cli.main(["--config", str(config_path), "publisher-check-all"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"platform": "x"' in output
    assert "dry-run mode" in output


def test_cli_demo_generate_review_and_publish_flow(tmp_path: Path, capsys) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "demo.md").write_text(
        """---
title: Demo Article
tags:
  - agents
---
# Demo Article

Local knowledge can become reviewable social content.
""",
        encoding="utf-8",
    )
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        f"""
environment: test
log_level: INFO
llm:
  provider: demo
  model: demo-local-deterministic
openviking:
  knowledge_base_path: {knowledge}
publishers:
  x:
    enabled: true
    dry_run: true
memory:
  storage_path: {tmp_path / "memory.jsonl"}
  skill_proposals_path: {tmp_path / "skill_proposals.jsonl"}
scheduler: {{}}
""",
        encoding="utf-8",
    )

    generate_code = cli.main(
        [
            "--config",
            str(config_path),
            "generate-once",
            "--content-type",
            "daily_summary",
            "--platform",
            "x",
        ]
    )
    container = cli.build_container(str(config_path))
    pending = container.memory.list_content(status=ReviewStatus.PENDING_REVIEW, platform="x")
    pending[0].status = ReviewStatus.APPROVED
    container.memory.update_content(pending[0])
    publish_code = cli.main(
        ["--config", str(config_path), "publish-approved", "--platform", "x"]
    )

    output = capsys.readouterr().out
    published = container.memory.get_content(pending[0].id)
    assert generate_code == 0
    assert publish_code == 0
    assert '"dry_run": true' in output
    assert published.status == ReviewStatus.PUBLISHED
