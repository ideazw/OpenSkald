from pathlib import Path

from backend.app.domain.models import ContentType, GeneratedContent, ReviewStatus
from backend.app.memory.store import MemoryStore


def test_memory_updates_review_status(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Daily",
        body="Thread",
    )
    memory.remember_content(content)

    content.status = ReviewStatus.APPROVED
    memory.update_content(content)

    loaded = memory.get_content(content.id)
    assert loaded is not None
    assert loaded.status == ReviewStatus.APPROVED


def test_memory_lists_content_by_status_and_platform(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    pending_x = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="X",
        body="Draft",
    )
    approved_wechat = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="wechat",
        title="WeChat",
        body="Ready",
        status=ReviewStatus.APPROVED,
    )
    memory.remember_content(pending_x)
    memory.remember_content(approved_wechat)

    assert [item.id for item in memory.list_content(status=ReviewStatus.PENDING_REVIEW)] == [
        pending_x.id
    ]
    assert [item.id for item in memory.list_content(platform="wechat")] == [approved_wechat.id]


def test_memory_content_summary_includes_recent_failures(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    failed = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Failed",
        body="Thread",
        status=ReviewStatus.APPROVED,
        metadata={"last_publish_error": {"type": "RuntimeError", "message": "no token"}},
    )
    published = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="blog",
        title="Published",
        body="Post",
        status=ReviewStatus.PUBLISHED,
    )
    memory.remember_content(failed)
    memory.remember_content(published)

    summary = memory.content_summary()

    assert summary["total"] == 2
    assert summary["by_status"]["approved"] == 1
    assert summary["by_status"]["published"] == 1
    assert summary["by_platform"]["x"] == 1
    assert summary["failed"] == 1
    assert summary["recent_failures"][0]["id"] == failed.id


def test_memory_timeline_and_search(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.jsonl", tmp_path / "skills.jsonl")
    x_content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="RAG Thread",
        body="Retrieval quality matters.",
        metadata={"skill": "x_writer"},
    )
    blog_content = GeneratedContent(
        content_type=ContentType.DEEP_TECHNICAL_ANALYSIS,
        platform="blog",
        title="Agent Memory",
        body="Memory accumulation improves review.",
    )
    memory.remember_content(x_content)
    memory.remember_content(blog_content)

    timeline = memory.timeline(platform="x")
    matches = memory.search_content("retrieval")

    assert timeline[0]["id"] == x_content.id
    assert timeline[0]["skill"] == "x_writer"
    assert [item.id for item in matches] == [x_content.id]
