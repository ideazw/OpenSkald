from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from backend.app.config.settings import LLMConfig, resolve_secret


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text from a model-compatible provider."""


class LLMProviderError(RuntimeError):
    """Raised when the configured LLM provider cannot generate text."""


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        config: LLMConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.api_key = resolve_secret(config.api_key_env)
        self.transport = transport

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LLMProviderError(f"Missing LLM API key env var: {self.config.api_key_env}")
        headers = {"Content-Type": "application/json"}
        headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }
        async with httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            transport=self.transport,
        ) as client:
            try:
                response = await client.post(
                    f"{self.config.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.RequestError as error:
                raise LLMProviderError(f"LLM provider request failed: {error}") from error
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                detail = response.text[:1000]
                raise LLMProviderError(
                    f"LLM provider returned HTTP {response.status_code}: {detail}"
                ) from error
            data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMProviderError("LLM provider returned an unexpected response shape") from error


class DemoLLMProvider(LLMProvider):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        task_prompt = system_prompt.lower()
        full_prompt = f"{system_prompt}\n{user_prompt}".lower()
        if "xiaohongshu" in task_prompt:
            return (
                "Title options:\n"
                "1. RAG Agent Notes\n"
                "2. AI Content Ops Starter\n"
                "3. Knowledge Base to Posts\n\n"
                "Note:\n"
                "Local knowledge bases can power repeatable content workflows when retrieval, "
                "memory, review, and publishing stay modular.\n\n"
                "Tags: #AI #RAG #ContentOps\n\n"
                "Cover image prompts:\n"
                "1. Clean desk with knowledge graph and content calendar\n"
                "2. Minimal dashboard showing review queue\n"
                "3. Technical notes transforming into social posts"
            )
        if "x threads" in task_prompt or "x thread" in full_prompt:
            return (
                "1/ Local knowledge bases are a strong foundation for content automation.\n"
                "2/ Keep retrieval, skills, review, and publishing as separate modules.\n"
                "3/ Human approval is the safety gate before any platform publish.\n"
                "4/ Start with dry-run publishers, then replace adapters one by one."
            )
        if "blog" in task_prompt or "wechat" in task_prompt or "markdown article" in task_prompt:
            return (
                "# Demo Technical Brief\n\n"
                "## Executive Summary\n\n"
                "This demo article shows how OpenViking Content Agent turns a local knowledge "
                "base into reviewable long-form technical content. It preserves source context, "
                "keeps claims grounded, and gives the reviewer a clear draft before publishing.\n\n"
                "## Technical Context\n\n"
                "The source notes discuss retrieval quality, agent memory, and lightweight "
                "automation. The useful pattern is to keep ingestion, prompting, review, and "
                "publishing as separate replaceable modules.\n\n"
                "## Practical Takeaway\n\n"
                "Start with dry-run publishing, inspect the review queue, then enable one real "
                "platform adapter at a time."
            )
        return (
            "1/ Local knowledge bases are a strong foundation for content automation.\n"
            "2/ Keep retrieval, skills, review, and publishing as separate modules.\n"
            "3/ Human approval is the safety gate before any platform publish.\n"
            "4/ Start with dry-run publishers, then replace adapters one by one."
        )


def build_llm_provider(config: LLMConfig) -> LLMProvider:
    if config.provider == "demo":
        return DemoLLMProvider()
    if config.provider in {"openai", "deepseek"}:
        return OpenAICompatibleProvider(config)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
