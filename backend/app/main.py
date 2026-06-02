from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.routes import build_router
from backend.app.bootstrap import AppContainer, build_container


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container: AppContainer = app.state.container
    if container.scheduler.get_jobs():
        container.scheduler.start()
    try:
        yield
    finally:
        if container.scheduler.running:
            container.scheduler.shutdown(wait=False)


def create_app(config_path: str | None = None) -> FastAPI:
    container = build_container(config_path)
    logging.basicConfig(
        level=getattr(logging, container.config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app = FastAPI(title="OpenViking Content Agent", version="0.1.0", lifespan=lifespan)
    app.state.container = container
    app.include_router(build_router(container), prefix="/api")
    return app


app = create_app()
