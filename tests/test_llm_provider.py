import httpx
import pytest

from backend.app.config.settings import LLMConfig, PublisherConfig
from backend.app.domain.models import ContentType, GeneratedContent
from backend.app.llm.provider import DemoLLMProvider, OpenAICompatibleProvider
from backend.app.publishers.x.publisher import PluginPublisher as XPublisher


@pytest.mark.asyncio
async def test_openai_compatible_provider_posts_chat_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    monkeypatch.setenv("TEST_LLM_KEY", "secret")

    provider = OpenAICompatibleProvider(
        LLMConfig(
            provider="cc_switch",
            base_url="http://llm-gateway.local/v1",
            api_key_env="TEST_LLM_KEY",
            model="configured-model",
        ),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate("system", "user")

    assert result == "ok"
    assert captured["url"] == "http://llm-gateway.local/v1/chat/completions"
    assert captured["auth"] == "Bearer secret"
    assert "configured-model" in captured["json"]


@pytest.mark.asyncio
async def test_demo_provider_x_output_passes_thread_validation() -> None:
    provider = DemoLLMProvider()
    body = await provider.generate(
        "You write sharp technical X threads that are clear, credible, and shareable.",
        "Articles mention WeChat, Markdown, blog, and Xiaohongshu.",
    )
    publisher = XPublisher(PublisherConfig(dry_run=True))
    publisher.platform = "x"
    content = GeneratedContent(
        content_type=ContentType.DAILY_SUMMARY,
        platform="x",
        title="Thread",
        body=body,
    )

    result = publisher.validate(content)

    assert result.ok
    assert body.startswith("1/")
