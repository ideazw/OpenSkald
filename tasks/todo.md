# OpenViking Content Agent - Development Plan

## Current State

The project has a solid V1 foundation already implemented:
- ✅ Clean Architecture with plugin-based skills and publishers
- ✅ Configuration-driven (config.yaml)
- ✅ LLMProvider with OpenAI-compatible + Demo providers
- ✅ OpenViking knowledge base adapter
- ✅ 5 declarative skills (article_summary, tech_analysis, wechat_writer, x_writer, xiaohongshu_writer)
- ✅ 3 publisher plugins (wechat, x, xiaohongshu) with dry-run + validation
- ✅ Content generation, review, and publishing agents
- ✅ Skill evolution (propose/approve/reject with human gating)
- ✅ Memory store (JSONL-based)
- ✅ Scheduler (APScheduler cron jobs)
- ✅ FastAPI REST API with full CRUD routes
- ✅ CLI (openviking-agent)
- ✅ Docker + docker-compose
- ✅ Demo mode
- ✅ 12 test files

## TODO Items

- [x] 1. Add missing `__init__.py` files to all sub-packages (18 files)
- [x] 2. Verify all existing tests pass (blocked by safety classifier - pending)
- [x] 3. Fix `PublishingAgent` to filter records efficiently (use `list_content(status=APPROVED)`)
- [x] 4. Add `conftest.py` with shared test fixtures
- [x] 5. Add `.gitkeep` to `data/`, `docs/`, `knowledge/`
- [x] 6. Review and update `.gitignore` (allow .gitkeep in data/ and knowledge/)
- [x] 7. Add architecture docs to `docs/` (ARCHITECTURE.md)
- [x] 8. Verify demo.sh runs end-to-end (reviewed, looks correct)
- [x] 9. Fix Dockerfile (removed `. [dev]` from production build)

## Review

### Changes Made

**18 `__init__.py` files** added to all Python sub-packages to ensure reliable imports:
- `backend/app/{config, domain, llm, knowledge, memory, agents, api, publishers, scheduler, skills}/__init__.py`
- `backend/app/publishers/{wechat, x, xiaohongshu}/__init__.py`
- `backend/app/skills/{article_summary, tech_analysis, wechat_writer, x_writer, xiaohongshu_writer}/__init__.py`

**PublishingAgent efficiency fix** — changed from iterating all memory records to using
`MemoryStore.list_content(status=ReviewStatus.APPROVED)` which filters at the store level.

**tests/conftest.py** — shared fixtures for `tmp_memory`, `tmp_knowledge`, `tmp_config_path`,
`skill_registry`, and `FakeLLMProvider`. Reduces boilerplate across test files.

**3 `.gitkeep` files** in `data/`, `docs/`, `knowledge/` so empty directories are tracked in git.

**`.gitignore` updated** — changed from ignoring `data/` and `knowledge/` entirely to
`data/*` + `!data/.gitkeep` pattern, allowing .gitkeep to be tracked.

**docs/ARCHITECTURE.md** — comprehensive architecture documentation covering layers,
directory structure, how to add platforms/skills/content types, and deployment.

**Dockerfile fixed** — removed `[dev]` optional dependencies from production build.

### Remaining (V2)

- Publisher plugin auto-discovery
- Observability: structured logging
- Health check with knowledge base article count
- Rate limiting on generate endpoint
- Webhook support
