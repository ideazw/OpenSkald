from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from backend.app.config.settings import PublisherConfig, resolve_secret
from backend.app.domain.models import GeneratedContent, PublishResult, PublishValidationResult
from backend.app.publishers.base import Publisher

logger = logging.getLogger(__name__)

XHS_API_BASE = "https://edith.xiaohongshu.com"


class PluginPublisher(Publisher):
    def __init__(self, config: PublisherConfig) -> None:
        super().__init__(config)
        self._credentials: dict[str, Any] | None = None

    def _get_credentials(self) -> dict[str, Any]:
        if self._credentials is None:
            raw = resolve_secret(self.config.credentials_env)
            if raw:
                try:
                    self._credentials = json.loads(raw)
                except json.JSONDecodeError:
                    self._credentials = {}
            else:
                self._credentials = {}
        return self._credentials

    def validate(self, content: GeneratedContent) -> PublishValidationResult:
        result = super().validate(content)
        errors = list(result.errors)
        if "cover" not in content.body.lower():
            errors.append("xiaohongshu content should include cover image prompts")
        if len(content.title) > 40:
            errors.append("xiaohongshu title should be 40 characters or fewer")
        return PublishValidationResult(ok=not errors, errors=errors)

    async def check(self) -> dict:
        base = await super().check()
        if self.config.dry_run:
            return {**base, "message": "dry-run mode; Xiaohongshu API was not contacted"}

        creds = self._get_credentials()
        cookie = creds.get("cookie")
        if not cookie:
            return {**base, "ok": False, "message": "missing credentials: cookie"}

        return {
            **base,
            "ok": True,
            "cookie_configured": True,
            "message": (
                "cookie is configured; Xiaohongshu publishing uses the experimental "
                "creator web adapter and should be verified with a real note publish"
            ),
        }

    async def publish(self, content: GeneratedContent) -> PublishResult:
        if self.config.dry_run:
            return PublishResult(
                platform=self.platform,
                dry_run=True,
                content_id=content.id,
                title=content.title,
                metadata={"account_id": self.config.account_id},
            )

        creds = self._get_credentials()
        cookie = creds.get("cookie")
        if not cookie:
            logger.error("Xiaohongshu cookie is missing from credentials")
            raise RuntimeError("Xiaohongshu cookie is required for publishing")

        note_body, tags, cover_prompts = self._parse_body(content.body)

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Cookie": cookie,
            "Content-Type": "application/json",
            "Origin": "https://creator.xiaohongshu.com",
            "Referer": "https://creator.xiaohongshu.com/publish/publish",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            image_urls = await self._upload_covers(client, headers, cover_prompts)
            result = await self._create_note(
                client, headers, content.title, note_body, tags, image_urls
            )

        note_id = result.get("id", "")
        return PublishResult(
            platform=self.platform,
            dry_run=False,
            content_id=content.id,
            external_id=note_id,
            url=f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else None,
            title=content.title,
            metadata={
                "account_id": self.config.account_id,
                "note_id": note_id,
                "tags": tags,
            },
        )

    async def _upload_covers(
        self, client: httpx.AsyncClient, headers: dict[str, str], cover_prompts: list[str]
    ) -> list[str]:
        image_urls: list[str] = []
        for prompt in cover_prompts[:1]:
            try:
                resp = await client.post(
                    f"{XHS_API_BASE}/api/sns/web/v1/image/upload",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "file_content": prompt,
                        "image_type": "WEBP",
                        "width": 1080,
                        "height": 1440,
                    },
                )
                data = resp.json()
                if data.get("success", False):
                    image_urls.append(data.get("data", {}).get("url", ""))
                else:
                    logger.warning("Xiaohongshu image upload failed: %s", data)
            except Exception:
                logger.warning("Xiaohongshu image upload error for prompt: %s", prompt[:50])
        return image_urls

    async def _create_note(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        title: str,
        body: str,
        tags: list[str],
        image_urls: list[str],
    ) -> dict[str, Any]:
        payload = {
            "title": title,
            "desc": body,
            "type": "normal",
            "image_info_list": [
                {
                    "image_url": url,
                    "width": 1080,
                    "height": 1440,
                }
                for url in image_urls
            ],
            "tag_list": tags,
        }
        resp = await client.post(
            f"{XHS_API_BASE}/api/sns/web/v1/note/create",
            headers=headers,
            json=payload,
        )
        data = resp.json()
        if data.get("success", False) is False:
            logger.error("Xiaohongshu note creation failed: %s", data)
            raise RuntimeError(f"Xiaohongshu note creation failed: {data.get('msg', 'unknown')}")
        return data.get("data", {})

    @staticmethod
    def _parse_body(body: str) -> tuple[str, list[str], list[str]]:
        lines = body.split("\n")
        note_lines: list[str] = []
        tags: list[str] = []
        cover_prompts: list[str] = []
        in_covers = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            tag_match = re.findall(r"#(\S+?)(?:\s|$)", stripped)
            tags.extend(tag_match)

            if "cover image prompts" in stripped.lower() or "封面" in stripped:
                in_covers = True
                continue
            if in_covers and re.match(r"^\d+\.", stripped):
                prompt = re.sub(r"^\d+\.\s*", "", stripped)
                cover_prompts.append(prompt)
                continue
            if in_covers and not re.match(r"^\d+\.", stripped):
                in_covers = False

            if not in_covers:
                note_lines.append(stripped)

        return "\n".join(note_lines), list(set(tags)), cover_prompts
