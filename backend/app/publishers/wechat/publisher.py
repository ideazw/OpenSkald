from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from backend.app.config.settings import PublisherConfig, resolve_secret
from backend.app.domain.models import GeneratedContent, PublishResult, PublishValidationResult
from backend.app.publishers.base import Publisher

logger = logging.getLogger(__name__)

ACCESS_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
PUBLISH_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"
UPLOAD_IMAGE_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"


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
        if not content.body.lstrip().startswith("#"):
            errors.append("wechat content should be Markdown with a heading")
        if len(content.body) < 200:
            errors.append("wechat long-form content should be at least 200 characters")
        return PublishValidationResult(ok=not errors, errors=errors)

    async def check(self) -> dict:
        base = await super().check()
        if self.config.dry_run:
            return {**base, "message": "dry-run mode; WeChat API was not contacted"}

        creds = self._get_credentials()
        app_id = creds.get("app_id")
        app_secret = creds.get("app_secret")
        thumb_media_id = creds.get("thumb_media_id")
        missing = [
            name
            for name, value in {
                "app_id": app_id,
                "app_secret": app_secret,
                "thumb_media_id": thumb_media_id,
            }.items()
            if not value
        ]
        if missing:
            return {**base, "ok": False, "message": f"missing credentials: {', '.join(missing)}"}

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                access_token = await self._get_access_token(
                    client,
                    str(app_id),
                    str(app_secret),
                )
            except RuntimeError as error:
                return {**base, "ok": False, "message": str(error)}
        return {
            **base,
            "ok": True,
            "app_id_configured": True,
            "thumb_media_id_configured": True,
            "access_token_verified": bool(access_token),
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
        app_id = creds.get("app_id")
        app_secret = creds.get("app_secret")
        thumb_media_id = creds.get("thumb_media_id")

        if not app_id or not app_secret:
            logger.error(
                "WeChat credentials missing: app_id=%s has_secret=%s",
                bool(app_id),
                bool(app_secret),
            )
            raise RuntimeError("WeChat app_id and app_secret are required for publishing")
        if not thumb_media_id:
            raise RuntimeError("WeChat thumb_media_id is required for publishing")

        async with httpx.AsyncClient(timeout=30) as client:
            access_token = await self._get_access_token(client, app_id, app_secret)
            draft_result = await self._create_draft(
                client,
                access_token,
                content,
                thumb_media_id,
            )
            media_id_str = draft_result.get("media_id", "")

            publish_resp = await client.post(
                PUBLISH_URL,
                params={"access_token": access_token},
                json={"media_id": media_id_str},
            )
            publish_data = publish_resp.json()

            if publish_data.get("errcode", 0) != 0:
                logger.error("WeChat publish failed: %s", publish_data)
                message = publish_data.get("errmsg", "unknown")
                raise RuntimeError(f"WeChat publish failed: {message}")

            publish_id = publish_data.get("publish_id", media_id_str)

        return PublishResult(
            platform=self.platform,
            dry_run=False,
            content_id=content.id,
            external_id=publish_id,
            title=content.title,
            metadata={"account_id": self.config.account_id, "media_id": media_id_str},
        )

    async def _get_access_token(
        self,
        client: httpx.AsyncClient,
        app_id: str,
        app_secret: str,
    ) -> str:
        resp = await client.get(
            ACCESS_TOKEN_URL,
            params={"grant_type": "client_credential", "appid": app_id, "secret": app_secret},
        )
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"WeChat token failed: {data.get('errmsg', 'unknown')}")
        return data["access_token"]

    async def _create_draft(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        content: GeneratedContent,
        thumb_url: str,
    ) -> dict[str, Any]:
        articles = [{
            "title": content.title,
            "author": self.config.account_id or "",
            "digest": content.body[:120],
            "content": self._markdown_to_html(content.body),
            "content_source_url": "",
            "thumb_media_id": thumb_url,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }]
        resp = await client.post(
            DRAFT_URL,
            params={"access_token": access_token},
            json={"articles": articles},
        )
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"WeChat draft failed: {data.get('errmsg', 'unknown')}")
        return data

    @staticmethod
    def _markdown_to_html(md: str) -> str:
        lines = md.split("\n")
        html_parts: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                html_parts.append("")
                continue
            if stripped.startswith("### "):
                html_parts.append(f"<h3>{stripped[4:]}</h3>")
            elif stripped.startswith("## "):
                html_parts.append(f"<h2>{stripped[3:]}</h2>")
            elif stripped.startswith("# "):
                html_parts.append(f"<h1>{stripped[2:]}</h1>")
            elif stripped.startswith("- "):
                html_parts.append(f"<p>• {stripped[2:]}</p>")
            elif stripped.startswith("```"):
                continue
            else:
                html_parts.append(f"<p>{stripped}</p>")
        return "\n".join(html_parts)
