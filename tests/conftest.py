from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from price_intel.database import create_engine, create_session_factory, init_db
from price_intel.extractors import BrowserPool, ExtractorRegistry, HttpExtractor
from price_intel.queue import SQLiteTaskQueue
from price_intel.service import ExtractionService
from price_intel.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        max_http_concurrency=5,
        max_browser_contexts=1,
        request_timeout_seconds=5,
        default_retry_budget=1,
    )


@pytest.fixture
async def session_factory(settings: Settings) -> async_sessionmaker:
    engine = create_engine(settings)
    await init_db(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


def mock_client(
    html: str = "<html><h1>$12.50</h1></html>",
    status_code: int = 200,
) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, text=html, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
async def extraction_service(
    settings: Settings,
    session_factory: async_sessionmaker,
) -> ExtractionService:
    client = mock_client("<html><h1>$12.50</h1><a href='/buy'>Buy</a></html>")
    registry = ExtractorRegistry(HttpExtractor(client, settings), BrowserPool(settings))
    queue = SQLiteTaskQueue(session_factory, settings)
    try:
        yield ExtractionService(queue, registry, session_factory)
    finally:
        await registry.stop()
        await client.aclose()
