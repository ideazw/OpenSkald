from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from backend.app.config.settings import OpenVikingConfig
from backend.app.domain.models import Article


class OpenVikingKnowledgeBase:
    """Reads technical articles from a local OpenViking-exported folder."""

    def __init__(self, config: OpenVikingConfig) -> None:
        self.config = config

    def recent_articles(self) -> list[Article]:
        root = self.config.knowledge_base_path
        if not root.exists():
            return []

        paths: list[Path] = []
        for pattern in self.config.include_globs:
            paths.extend(root.glob(pattern))

        files = sorted({path for path in paths if path.is_file()}, key=lambda p: p.stat().st_mtime)
        articles = [self._load_article(path) for path in files[-self.config.max_articles_per_run :]]
        return [article for article in articles if article.content.strip()]

    def _load_article(self, path: Path) -> Article:
        text = path.read_text(encoding="utf-8")
        metadata: dict[str, object] = {}
        content = text
        if path.suffix.lower() == ".md":
            metadata, content = _split_front_matter(text)

        title = str(metadata.get("title") or path.stem.replace("-", " ").replace("_", " ").title())
        article_id = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
        tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
        return Article(
            id=article_id,
            title=title,
            content=content,
            source_path=str(path),
            url=str(metadata.get("url")) if metadata.get("url") else None,
            tags=[str(tag) for tag in tags],
        )


def _split_front_matter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    _, raw_metadata, content = text.split("---", 2)
    metadata = yaml.safe_load(raw_metadata) or {}
    if not isinstance(metadata, dict):
        return {}, content.lstrip()
    return metadata, content.lstrip()
