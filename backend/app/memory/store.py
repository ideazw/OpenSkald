from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from backend.app.domain.models import Article, GeneratedContent, ReviewStatus, SkillProposal


class JsonlStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, item: BaseModel) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(item.model_dump_json() + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def replace_all(self, rows: list[dict]) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")


class MemoryStore:
    def __init__(
        self,
        memory_path: Path,
        skill_proposals_path: Path,
        article_index_path: Path | None = None,
    ) -> None:
        self.memory = JsonlStore(memory_path)
        self.skill_proposals = JsonlStore(skill_proposals_path)
        self.articles = JsonlStore(article_index_path or memory_path.parent / "articles.jsonl")

    def remember_article(self, article: Article) -> None:
        records = self.articles.read_all()
        serialized = article.model_dump(mode="json")
        for index, record in enumerate(records):
            if record.get("id") == article.id:
                records[index] = serialized
                self.articles.replace_all(records)
                return
        records.append(serialized)
        self.articles.replace_all(records)

    def list_articles(self) -> list[Article]:
        return [Article.model_validate(record) for record in self.articles.read_all()]

    def search_articles(self, query: str, limit: int = 20) -> list[Article]:
        needle = query.lower().strip()
        if not needle:
            return []
        matches = []
        for article in self.list_articles():
            haystack = " ".join([article.title, article.content, " ".join(article.tags)]).lower()
            if needle in haystack:
                matches.append(article)
        return matches[:limit]

    def remember_content(self, content: GeneratedContent) -> None:
        self.memory.append(content)

    def get_content(self, content_id: str) -> GeneratedContent | None:
        records = self.memory.read_all()
        match = next((record for record in records if record.get("id") == content_id), None)
        return GeneratedContent.model_validate(match) if match else None

    def list_content(
        self,
        status: ReviewStatus | None = None,
        platform: str | None = None,
    ) -> list[GeneratedContent]:
        content = [GeneratedContent.model_validate(record) for record in self.memory.read_all()]
        if status:
            content = [item for item in content if item.status == status]
        if platform:
            content = [item for item in content if item.platform == platform]
        return content

    def list_failed_content(self, platform: str | None = None) -> list[GeneratedContent]:
        content = self.list_content(platform=platform)
        return [
            item
            for item in content
            if item.metadata.get("last_publish_error")
            or item.metadata.get("publish_validation_errors")
        ]

    def content_summary(self) -> dict:
        content = self.list_content()
        by_status = {status.value: 0 for status in ReviewStatus}
        by_platform: dict[str, int] = {}
        for item in content:
            by_status[item.status.value] = by_status.get(item.status.value, 0) + 1
            by_platform[item.platform] = by_platform.get(item.platform, 0) + 1
        failures = self.list_failed_content()
        return {
            "total": len(content),
            "by_status": by_status,
            "by_platform": by_platform,
            "failed": len(failures),
            "recent_failures": [
                {
                    "id": item.id,
                    "platform": item.platform,
                    "title": item.title,
                    "status": item.status.value,
                    "last_publish_error": item.metadata.get("last_publish_error"),
                    "publish_validation_errors": item.metadata.get(
                        "publish_validation_errors",
                        [],
                    ),
                }
                for item in failures[-10:]
            ],
        }

    def operational_summary(self) -> dict:
        content_summary = self.content_summary()
        proposals = self.list_skill_proposals()
        proposals_by_status = {status.value: 0 for status in ReviewStatus}
        for proposal in proposals:
            proposals_by_status[proposal.status.value] = (
                proposals_by_status.get(proposal.status.value, 0) + 1
            )
        return {
            "articles": {
                "total": len(self.list_articles()),
            },
            "content": content_summary,
            "skill_proposals": {
                "total": len(proposals),
                "by_status": proposals_by_status,
            },
        }

    def timeline(self, limit: int = 20, platform: str | None = None) -> list[dict]:
        content = self.list_content(platform=platform)
        ordered = sorted(
            content,
            key=lambda item: item.published_at or item.reviewed_at or item.created_at,
            reverse=True,
        )
        return [self._memory_event(item) for item in ordered[:limit]]

    def search_content(self, query: str, limit: int = 20) -> list[GeneratedContent]:
        needle = query.lower().strip()
        if not needle:
            return []
        matches = []
        for item in self.list_content():
            haystack = " ".join(
                [
                    item.title,
                    item.body,
                    item.platform,
                    item.content_type.value,
                    json.dumps(item.metadata, ensure_ascii=False),
                ]
            ).lower()
            if needle in haystack:
                matches.append(item)
        return matches[:limit]

    def _memory_event(self, item: GeneratedContent) -> dict:
        return {
            "id": item.id,
            "content_type": item.content_type.value,
            "platform": item.platform,
            "title": item.title,
            "status": item.status.value,
            "created_at": item.created_at.isoformat(),
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "skill": item.metadata.get("skill"),
            "last_publish_error": item.metadata.get("last_publish_error"),
        }

    def update_content(self, content: GeneratedContent) -> None:
        records = self.memory.read_all()
        updated = False
        for index, record in enumerate(records):
            if record.get("id") == content.id:
                records[index] = content.model_dump(mode="json")
                updated = True
                break
        if not updated:
            records.append(content.model_dump(mode="json"))
        self.memory.replace_all(records)

    def store_skill_proposal(self, proposal: SkillProposal) -> None:
        self.skill_proposals.append(proposal)

    def get_skill_proposal(self, proposal_id: str) -> SkillProposal | None:
        records = self.skill_proposals.read_all()
        match = next((record for record in records if record.get("id") == proposal_id), None)
        return SkillProposal.model_validate(match) if match else None

    def list_skill_proposals(
        self,
        status: ReviewStatus | None = None,
    ) -> list[SkillProposal]:
        proposals = [
            SkillProposal.model_validate(record) for record in self.skill_proposals.read_all()
        ]
        if status:
            proposals = [proposal for proposal in proposals if proposal.status == status]
        return proposals

    def update_skill_proposal(self, proposal: SkillProposal) -> None:
        records = self.skill_proposals.read_all()
        updated = False
        for index, record in enumerate(records):
            if record.get("id") == proposal.id:
                records[index] = proposal.model_dump(mode="json")
                updated = True
                break
        if not updated:
            records.append(proposal.model_dump(mode="json"))
        self.skill_proposals.replace_all(records)
