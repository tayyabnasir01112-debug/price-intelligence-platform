from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI

from price_intel.api import routes
from price_intel.database import create_engine, create_session_factory, init_db
from price_intel.extractors import BrowserPool, ExtractorRegistry, HttpExtractor
from price_intel.logging import configure_logging
from price_intel.queue import SQLiteTaskQueue
from price_intel.service import ExtractionService
from price_intel.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    http_client = httpx.AsyncClient()
    browser_pool = BrowserPool(settings)
    registry = ExtractorRegistry(HttpExtractor(http_client, settings), browser_pool)
    queue = SQLiteTaskQueue(session_factory, settings)
    service = ExtractionService(queue, registry, session_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await init_db(engine)
        try:
            yield
        finally:
            await registry.stop()
            await http_client.aclose()
            await engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.http_client = http_client
    app.state.registry = registry
    app.state.service = service

    app.dependency_overrides[routes.get_service] = lambda: service
    app.dependency_overrides[routes.get_engine] = lambda: engine
    app.dependency_overrides[routes.get_settings_dep] = lambda: settings

    app.include_router(routes.router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run("price_intel.main:app", host="0.0.0.0", port=8000, reload=False)
