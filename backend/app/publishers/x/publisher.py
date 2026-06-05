from __future__ import annotations

import json
import logging
import secrets
import time
from base64 import b64encode
from hashlib import sha1
from hmac import new as hmac_new
from typing import Any
from urllib.parse import quote

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

        headers = self._auth_headers("GET", ME_URL)
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

        posts = [line.strip() for line in content.body.splitlines() if line.strip()]
        tweet_ids: list[str] = []

        async with httpx.AsyncClient(timeout=30) as client:
            for index, post in enumerate(posts):
                payload: dict[str, Any] = {"text": post}
                if tweet_ids:
                    payload["reply"] = {"in_reply_to_tweet_id": tweet_ids[-1]}

                headers = self._auth_headers("POST", TWEET_URL)
                headers["Content-Type"] = "application/json"
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

    def _auth_headers(self, method: str, url: str) -> dict[str, str]:
        creds = self._get_credentials()
        user_access_token = creds.get("user_access_token")
        if user_access_token:
            return {"Authorization": f"Bearer {user_access_token}"}

        oauth1 = self._oauth1_credentials()
        return {"Authorization": _build_oauth1_authorization_header(method, url, oauth1)}

    def _oauth1_credentials(self) -> dict[str, str]:
        creds = self._get_credentials()
        aliases = {
            "consumer_key": ("consumer_key", "api_key", "oauth_consumer_key"),
            "consumer_secret": (
                "consumer_secret",
                "api_secret",
                "api_key_secret",
                "oauth_consumer_secret",
            ),
            "access_token": ("access_token", "oauth_token"),
            "access_token_secret": ("access_token_secret", "oauth_token_secret"),
        }
        resolved: dict[str, str] = {}
        missing: list[str] = []
        for target, keys in aliases.items():
            value = next((creds.get(key) for key in keys if creds.get(key)), None)
            if value:
                resolved[target] = str(value)
            else:
                missing.append(target)

        if missing:
            logger.error("X OAuth 1.0a credentials are missing keys: %s", ", ".join(missing))
            raise RuntimeError(
                "X credentials must include either user_access_token or OAuth 1.0a "
                f"keys: {', '.join(missing)}"
            )
        return resolved


def _percent_encode(value: str) -> str:
    return quote(value, safe="~")


def _build_oauth1_authorization_header(
    method: str,
    url: str,
    credentials: dict[str, str],
) -> str:
    oauth_params = {
        "oauth_consumer_key": credentials["consumer_key"],
        "oauth_nonce": secrets.token_urlsafe(24),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": credentials["access_token"],
        "oauth_version": "1.0",
    }
    encoded_params = "&".join(
        f"{_percent_encode(key)}={_percent_encode(value)}"
        for key, value in sorted(oauth_params.items())
    )
    signature_base = "&".join(
        [_percent_encode(method.upper()), _percent_encode(url), _percent_encode(encoded_params)]
    )
    signing_key = "&".join(
        [
            _percent_encode(credentials["consumer_secret"]),
            _percent_encode(credentials["access_token_secret"]),
        ]
    )
    digest = hmac_new(
        signing_key.encode("utf-8"),
        signature_base.encode("utf-8"),
        sha1,
    ).digest()
    oauth_params["oauth_signature"] = b64encode(digest).decode("ascii")
    header_params = ", ".join(
        f'{_percent_encode(key)}="{_percent_encode(value)}"'
        for key, value in sorted(oauth_params.items())
    )
    return f"OAuth {header_params}"
