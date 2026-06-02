from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from backend.app.config.settings import PublisherConfig
from backend.app.domain.models import ContentType, GeneratedContent
from backend.app.publishers.blog.publisher import PluginPublisher as BlogPublisher
from backend.app.publishers.wechat.publisher import PluginPublisher as WeChatPublisher
from backend.app.publishers.x.publisher import PluginPublisher as XPublisher
from backend.app.publishers.xiaohongshu.publisher import PluginPublisher as XiaohongshuPublisher


def test_x_publisher_validates_thread_length() -> None:
    publisher = XPublisher(PublisherConfig(dry_run=True))
    publisher.platform = "x"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Thread",
        body="short\n" + ("x" * 281),
    )

    result = publisher.validate(content)

    assert not result.ok
    assert "280 characters" in result.errors[0]


def test_wechat_publisher_requires_markdown_long_form() -> None:
    publisher = WeChatPublisher(PublisherConfig(dry_run=True))
    publisher.platform = "wechat"
    content = GeneratedContent(
        content_type=ContentType.DEEP_TECHNICAL_ANALYSIS,
        platform="wechat",
        title="Article",
        body="Too short",
    )

    result = publisher.validate(content)

    assert not result.ok
    assert "Markdown" in result.errors[0]


def test_xiaohongshu_publisher_requires_cover_prompt() -> None:
    publisher = XiaohongshuPublisher(PublisherConfig(dry_run=True))
    publisher.platform = "xiaohongshu"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="xiaohongshu",
        title="Note",
        body="No visual prompt here",
    )

    result = publisher.validate(content)

    assert not result.ok
    assert "cover image prompts" in result.errors[0]


def test_blog_publisher_validates_markdown_long_form() -> None:
    publisher = BlogPublisher(PublisherConfig(dry_run=True))
    publisher.platform = "blog"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="blog",
        title="Blog",
        body="Too short",
    )

    result = publisher.validate(content)

    assert not result.ok
    assert "Markdown" in result.errors[0]


@pytest.mark.asyncio
async def test_blog_publisher_writes_markdown_file(tmp_path: Path) -> None:
    publisher = BlogPublisher(
        PublisherConfig(enabled=True, dry_run=False, account_id=str(tmp_path)),
    )
    publisher.platform = "blog"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="blog",
        title="My Blog Post",
        body="# My Blog Post\n\n" + ("Useful technical content. " * 20),
    )

    result = await publisher.publish(content)

    output_path = Path(result.url)
    assert result.dry_run is False
    assert output_path.exists()
    assert "status: published" in output_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_x_publisher_dry_run_skips_api() -> None:
    publisher = XPublisher(PublisherConfig(dry_run=True, account_id="test-x"))
    publisher.platform = "x"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Dry Run",
        body="1/ Hello\n2/ World",
    )
    result = await publisher.publish(content)
    assert result.dry_run is True
    assert result.platform == "x"


@pytest.mark.asyncio
async def test_wechat_publisher_dry_run_skips_api() -> None:
    publisher = WeChatPublisher(PublisherConfig(dry_run=True, account_id="test-wechat"))
    publisher.platform = "wechat"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="wechat",
        title="# Dry Run Article",
        body="# Test\n\nLong enough content to pass validation.\n" + "x" * 200,
    )
    result = await publisher.publish(content)
    assert result.dry_run is True
    assert result.platform == "wechat"


@pytest.mark.asyncio
async def test_xiaohongshu_publisher_dry_run_skips_api() -> None:
    publisher = XiaohongshuPublisher(PublisherConfig(dry_run=True, account_id="test-xhs"))
    publisher.platform = "xiaohongshu"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="xiaohongshu",
        title="Note",
        body="Some content\n\nCover image prompts:\n1. A nice cover\n\nTags: #AI #RAG",
    )
    result = await publisher.publish(content)
    assert result.dry_run is True
    assert result.platform == "xiaohongshu"


@pytest.mark.asyncio
async def test_x_publisher_posts_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_TEST_CREDS", '{"user_access_token": "test_token"}')
    call_log: list[str] = []
    auth_log: list[str | None] = []

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, **kwargs) -> httpx.Response:
        call_log.append(str(url))
        auth_log.append(kwargs["headers"].get("Authorization"))
        return httpx.Response(201, json={"data": {"id": "1234567890"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    publisher = XPublisher(
        PublisherConfig(dry_run=False, account_id="test-x", credentials_env="X_TEST_CREDS"),
    )
    publisher.platform = "x"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Thread",
        body="First tweet\nSecond tweet\nThird tweet",
    )

    result = await publisher.publish(content)

    assert result.dry_run is False
    assert result.external_id == "1234567890"
    assert result.url == "https://x.com/i/status/1234567890"
    assert result.metadata["tweet_count"] == 3
    assert len(call_log) == 3
    assert call_log == ["https://api.x.com/2/tweets"] * 3
    assert auth_log == ["Bearer test_token"] * 3

    monkeypatch.setattr(httpx.AsyncClient, "post", original_post)


@pytest.mark.asyncio
async def test_x_publisher_check_uses_user_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_CHECK_CREDS", '{"user_access_token": "check_token"}')
    call_log: list[str] = []
    auth_log: list[str | None] = []

    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, **kwargs) -> httpx.Response:
        call_log.append(str(url))
        auth_log.append(kwargs["headers"].get("Authorization"))
        return httpx.Response(
            200,
            json={"data": {"id": "u_123", "username": "openviking", "name": "OpenViking"}},
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    publisher = XPublisher(
        PublisherConfig(enabled=True, dry_run=False, credentials_env="X_CHECK_CREDS"),
    )
    publisher.platform = "x"

    result = await publisher.check()

    assert result["ok"] is True
    assert result["username"] == "openviking"
    assert call_log == ["https://api.x.com/2/users/me"]
    assert auth_log == ["Bearer check_token"]

    monkeypatch.setattr(httpx.AsyncClient, "get", original_get)


@pytest.mark.asyncio
async def test_x_publisher_check_reports_api_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_CHECK_CREDS", '{"user_access_token": "bad_token"}')
    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, **kwargs) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    publisher = XPublisher(
        PublisherConfig(enabled=True, dry_run=False, credentials_env="X_CHECK_CREDS"),
    )
    publisher.platform = "x"

    result = await publisher.check()

    assert result["ok"] is False
    assert result["status_code"] == 401

    monkeypatch.setattr(httpx.AsyncClient, "get", original_get)


@pytest.mark.asyncio
async def test_x_publisher_fails_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_MISSING_CREDS", raising=False)
    publisher = XPublisher(
        PublisherConfig(dry_run=False, credentials_env="X_MISSING_CREDS"),
    )
    publisher.platform = "x"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Thread",
        body="Hello",
    )
    with pytest.raises(RuntimeError, match="user_access_token"):
        await publisher.publish(content)


@pytest.mark.asyncio
async def test_x_publisher_rejects_app_only_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_BEARER_ONLY_CREDS", '{"bearer_token": "app_only"}')
    publisher = XPublisher(
        PublisherConfig(dry_run=False, credentials_env="X_BEARER_ONLY_CREDS"),
    )
    publisher.platform = "x"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Thread",
        body="Hello",
    )
    with pytest.raises(RuntimeError, match="user_access_token"):
        await publisher.publish(content)


@pytest.mark.asyncio
async def test_wechat_publisher_creates_draft_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "WX_TEST_CREDS",
        '{"app_id": "test_id", "app_secret": "test_secret", "thumb_media_id": "thumb_123"}',
    )
    call_log: list[str] = []

    original_get = httpx.AsyncClient.get
    original_post = httpx.AsyncClient.post

    async def mock_get(self, url, **kwargs) -> httpx.Response:
        call_log.append(str(url))
        return httpx.Response(200, json={"access_token": "test_token"})

    async def mock_post(self, url, **kwargs) -> httpx.Response:
        call_log.append(str(url))
        url_str = str(url)
        if "draft/add" in url_str:
            return httpx.Response(200, json={"media_id": "draft_123"})
        if "freepublish/submit" in url_str:
            return httpx.Response(200, json={"publish_id": "pub_456"})
        return httpx.Response(400, json={"errcode": -1, "errmsg": "unknown"})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    publisher = WeChatPublisher(
        PublisherConfig(dry_run=False, account_id="test-mp", credentials_env="WX_TEST_CREDS"),
    )
    publisher.platform = "wechat"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="wechat",
        title="# WeChat Test",
        body="# WeChat Test\n\nSome content for the article.\n" + "x" * 200,
    )

    result = await publisher.publish(content)

    assert result.dry_run is False
    assert result.external_id == "pub_456"
    assert len(call_log) == 3

    monkeypatch.setattr(httpx.AsyncClient, "get", original_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", original_post)


@pytest.mark.asyncio
async def test_wechat_publisher_check_verifies_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "WX_CHECK_CREDS",
        '{"app_id": "test_id", "app_secret": "test_secret", "thumb_media_id": "thumb_123"}',
    )
    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, **kwargs) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "test_token"})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    publisher = WeChatPublisher(
        PublisherConfig(enabled=True, dry_run=False, credentials_env="WX_CHECK_CREDS"),
    )
    publisher.platform = "wechat"

    result = await publisher.check()

    assert result["ok"] is True
    assert result["access_token_verified"] is True

    monkeypatch.setattr(httpx.AsyncClient, "get", original_get)


@pytest.mark.asyncio
async def test_wechat_publisher_check_reports_missing_credentials() -> None:
    publisher = WeChatPublisher(PublisherConfig(enabled=True, dry_run=False))
    publisher.platform = "wechat"

    result = await publisher.check()

    assert result["ok"] is False
    assert "missing credentials" in result["message"]


@pytest.mark.asyncio
async def test_xiaohongshu_publisher_creates_note(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XHS_TEST_CREDS", '{"cookie": "test_cookie"}')

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, **kwargs) -> httpx.Response:
        url_str = str(url)
        if "image/upload" in url_str:
            return httpx.Response(200, json={"success": True, "data": {"url": "https://img.xhs.cn/c.jpg"}})
        if "note/create" in url_str:
            return httpx.Response(200, json={"success": True, "data": {"id": "note_abc"}})
        return httpx.Response(400, json={"success": False, "msg": "error"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    publisher = XiaohongshuPublisher(
        PublisherConfig(dry_run=False, account_id="test-xhs", credentials_env="XHS_TEST_CREDS"),
    )
    publisher.platform = "xiaohongshu"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="xiaohongshu",
        title="AI Tips",
        body="Learn AI basics.\n\nCover image prompts:\n1. Robot reading\n\nTags: #AI #Tips",
    )

    result = await publisher.publish(content)

    assert result.dry_run is False
    assert result.external_id == "note_abc"

    monkeypatch.setattr(httpx.AsyncClient, "post", original_post)


@pytest.mark.asyncio
async def test_xiaohongshu_publisher_check_requires_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XHS_CHECK_CREDS", '{"cookie": "test_cookie"}')
    publisher = XiaohongshuPublisher(
        PublisherConfig(enabled=True, dry_run=False, credentials_env="XHS_CHECK_CREDS"),
    )
    publisher.platform = "xiaohongshu"

    result = await publisher.check()

    assert result["ok"] is True
    assert result["cookie_configured"] is True


def test_wechat_markdown_to_html() -> None:
    md = "# Title\n\n## Sub\n\nSome text\n- bullet"
    html = WeChatPublisher._markdown_to_html(md)
    assert "<h1>Title</h1>" in html
    assert "<h2>Sub</h2>" in html
    assert "<p>Some text</p>" in html
    assert "<p>• bullet</p>" in html


def test_xiaohongshu_parse_body() -> None:
    body = "Intro text here\n\nCover image prompts:\n1. Cover A\n2. Cover B\n\nTags: #AI #RAG"
    note, tags, covers = XiaohongshuPublisher._parse_body(body)
    assert "Intro text here" in note
    assert "AI" in tags
    assert "RAG" in tags
    assert "Cover A" in covers
    assert "Cover B" in covers
