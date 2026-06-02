from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from backend.app.bootstrap import build_container
from backend.app.config.settings import config_summary
from backend.app.domain.models import ContentType, ReviewStatus
from backend.app.ops.status import operational_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openviking-agent")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml. Defaults to OPENVIKING_AGENT_CONFIG or config/config.yaml.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("config-summary", help="Print redacted config summary.")
    subcommands.add_parser("validate-config", help="Validate config and exit non-zero on errors.")
    subcommands.add_parser("status", help="Print operational status without contacting publishers.")

    generate = subcommands.add_parser("generate-once", help="Generate content once.")
    generate.add_argument(
        "--content-type",
        required=True,
        choices=[item.value for item in ContentType],
    )
    generate.add_argument("--platform", action="append", required=True, dest="platforms")

    subcommands.add_parser("knowledge-ingest", help="Ingest OpenViking articles into memory.")

    articles = subcommands.add_parser("knowledge-list", help="List ingested articles.")
    articles.add_argument("--query", default=None)
    articles.add_argument("--limit", type=int, default=20)

    review = subcommands.add_parser("review-list", help="List review queue items.")
    review.add_argument("--status", choices=[item.value for item in ReviewStatus], default=None)
    review.add_argument("--platform", default=None)

    content_summary = subcommands.add_parser("content-summary", help="Summarize content state.")
    content_summary.set_defaults(command="content-summary")

    failures = subcommands.add_parser("content-failures", help="List failed publish attempts.")
    failures.add_argument("--platform", default=None)

    timeline = subcommands.add_parser("memory-timeline", help="Show recent memory events.")
    timeline.add_argument("--platform", default=None)
    timeline.add_argument("--limit", type=int, default=20)

    search = subcommands.add_parser("memory-search", help="Search generated content memory.")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=20)

    subcommands.add_parser(
        "skills-discover",
        help="Discover skill proposals from memory without enabling them.",
    )

    approve = subcommands.add_parser("review-approve", help="Approve one content item.")
    approve.add_argument("--content-id", required=True)

    reject = subcommands.add_parser("review-reject", help="Reject one content item.")
    reject.add_argument("--content-id", required=True)
    reject.add_argument("--reason", required=True)

    publish = subcommands.add_parser("publish-approved", help="Publish approved content.")
    publish.add_argument("--platform", action="append", dest="platforms")

    publisher_check = subcommands.add_parser(
        "publisher-check",
        help="Check publisher configuration and credentials.",
    )
    publisher_check.add_argument("--platform", required=True)
    subcommands.add_parser(
        "publisher-check-all",
        help="Check every configured publisher without publishing content.",
    )

    publish_one = subcommands.add_parser("publish-content", help="Publish one approved item.")
    publish_one.add_argument("--content-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> int:
    container = build_container(args.config)

    if args.command == "config-summary":
        _print_json(config_summary(container.config, container.config_issues))
        return 0

    if args.command == "validate-config":
        _print_json({"ok": not container.has_config_errors(), "issues": _issues(container)})
        return 1 if container.has_config_errors() else 0

    if args.command == "status":
        status = operational_status(container)
        _print_json(status)
        return 0 if status["ok"] else 1

    if args.command == "generate-once":
        try:
            generated = await container.agent.generate(
                ContentType(args.content_type),
                args.platforms,
            )
        except ValueError as error:
            _print_json({"ok": False, "error": str(error)})
            return 1
        _print_json([item.model_dump(mode="json") for item in generated])
        return 0

    if args.command == "knowledge-ingest":
        _print_json(container.knowledge_ingestion_agent.ingest())
        return 0

    if args.command == "knowledge-list":
        articles = (
            container.memory.search_articles(query=args.query, limit=args.limit)
            if args.query
            else container.memory.list_articles()[: args.limit]
        )
        _print_json([article.model_dump(mode="json") for article in articles])
        return 0

    if args.command == "review-list":
        status = ReviewStatus(args.status) if args.status else None
        items = container.memory.list_content(status=status, platform=args.platform)
        _print_json([item.model_dump(mode="json") for item in items])
        return 0

    if args.command == "content-summary":
        _print_json(container.memory.content_summary())
        return 0

    if args.command == "content-failures":
        items = container.memory.list_failed_content(platform=args.platform)
        _print_json([item.model_dump(mode="json") for item in items])
        return 0

    if args.command == "memory-timeline":
        _print_json(container.memory.timeline(limit=args.limit, platform=args.platform))
        return 0

    if args.command == "memory-search":
        items = container.memory.search_content(query=args.query, limit=args.limit)
        _print_json([item.model_dump(mode="json") for item in items])
        return 0

    if args.command == "skills-discover":
        proposals = container.skill_evolution_agent.discover_proposals()
        _print_json([proposal.model_dump(mode="json") for proposal in proposals])
        return 0

    if args.command == "review-approve":
        content = container.memory.get_content(args.content_id)
        if content is None:
            _print_json({"ok": False, "error": "content not found"})
            return 1
        content.status = ReviewStatus.APPROVED
        container.memory.update_content(content)
        _print_json(content.model_dump(mode="json"))
        return 0

    if args.command == "review-reject":
        content = container.memory.get_content(args.content_id)
        if content is None:
            _print_json({"ok": False, "error": "content not found"})
            return 1
        content.status = ReviewStatus.REJECTED
        content.review_note = args.reason
        container.memory.update_content(content)
        _print_json(content.model_dump(mode="json"))
        return 0

    if args.command == "publish-approved":
        results = await container.publishing_agent.publish_approved(args.platforms)
        _print_json(results)
        return 0

    if args.command == "publisher-check":
        publisher = container.publishers.get(args.platform)
        result = await publisher.check()
        _print_json(result)
        return 0 if result.get("ok") else 1

    if args.command == "publisher-check-all":
        results = []
        for platform in container.publishers.names():
            publisher = container.publishers.get(platform)
            results.append(await publisher.check())
        _print_json(results)
        return 0 if all(result.get("ok") for result in results) else 1

    if args.command == "publish-content":
        content = container.memory.get_content(args.content_id)
        if content is None:
            _print_json({"ok": False, "error": "content not found"})
            return 1
        if content.status != ReviewStatus.APPROVED:
            _print_json({"ok": False, "error": "content is not approved"})
            return 1
        result = await container.publishing_agent.publish_content(content)
        if result is None:
            refreshed = container.memory.get_content(args.content_id)
            metadata = refreshed.metadata if refreshed else {}
            _print_json(
                {
                    "ok": False,
                    "errors": metadata.get("publish_validation_errors", []),
                    "last_publish_error": metadata.get("last_publish_error"),
                }
            )
            return 1
        _print_json(result)
        return 0

    raise ValueError(f"Unsupported command: {args.command}")


def _issues(container: Any) -> list[dict]:
    return [issue.model_dump() for issue in container.config_issues]


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
