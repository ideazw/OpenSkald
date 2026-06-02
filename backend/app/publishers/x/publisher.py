from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from backend.app.config.settings import PublisherConfig, resolve_secret
from backend.app.domain.models import GeneratedContent, PublishResult, PublishValidationResult
from backend.app.publishers.base import Publisher

logger = logging.getLogger(__name__)

TWEET_URL = "https://api.x.com/2/tweets"
ME_URL = "https://api.x.com/2/users/me"


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
        posts = [line.strip() for line in content.body.splitlines() if line.strip()]
        too_long = [index + 1 for index, post in enumerate(posts) if len(post) > 280]
        if too_long:
            errors.append(f"x posts exceed 280 characters at positions: {too_long}")
        return PublishValidationResult(ok=not errors, errors=errors)

    async def check(self) -> dict:
        base = await super().check()
        if self.config.dry_run:
            return {**base, "message": "dry-run mode; X API was not contacted"}

        user_access_token = self._user_access_token()
        headers = {"Authorization": f"Bearer {user_access_token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(ME_URL, headers=headers)
        if response.status_code != 200:
            return {
                **base,
                "ok": False,
                "status_code": response.status_code,
                "message": response.text,
            }
        data = response.json().get("data", {})
        return {
            **base,
            "ok": True,
            "user_id": data.get("id"),
            "username": data.get("username"),
            "name": data.get("name"),
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

        user_access_token = self._user_access_token()

        headers = {
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json",
        }

        posts = [line.strip() for line in content.body.splitlines() if line.strip()]
        tweet_ids: list[str] = []

        async with httpx.AsyncClient(timeout=30) as client:
            for index, post in enumerate(posts):
                payload: dict[str, Any] = {"text": post}
                if tweet_ids:
                    payload["reply"] = {"in_reply_to_tweet_id": tweet_ids[-1]}

                resp = await client.post(TWEET_URL, headers=headers, json=payload)

                if resp.status_code != 201:
                    logger.error("X tweet %d failed: %s", index, resp.text)
                    raise RuntimeError(f"X tweet {index + 1} failed: {resp.text}")

                data = resp.json()
                tweet_id = data["data"]["id"]
                tweet_ids.append(tweet_id)

        return PublishResult(
            platform=self.platform,
            dry_run=False,
            content_id=content.id,
            external_id=tweet_ids[0] if tweet_ids else None,
            url=f"https://x.com/i/status/{tweet_ids[0]}" if tweet_ids else None,
            title=content.title,
            metadata={
                "account_id": self.config.account_id,
                "tweet_count": len(tweet_ids),
                "tweet_ids": tweet_ids,
            },
        )

    def _user_access_token(self) -> str:
        creds = self._get_credentials()
        user_access_token = creds.get("user_access_token")
        if not user_access_token:
            logger.error("X user_access_token is missing from credentials")
            raise RuntimeError("X user_access_token is required for publishing")
        return str(user_access_token)
