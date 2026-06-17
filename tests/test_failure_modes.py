import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from price_intel.extractors import BrowserPool, ExtractorRegistry, HttpExtractor
from price_intel.orm import QueueTask
from price_intel.queue import SQLiteTaskQueue
from price_intel.schemas import ExtractionRequest, SelectorSpec, TargetConfig, TaskStatus
from price_intel.service import ExtractionService
from price_intel.settings import Settings


async def test_failed_extraction_respects_retry_budget(
    settings: Settings,
    session_factory: async_sessionmaker,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="bad gateway", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        registry = ExtractorRegistry(HttpExtractor(client, settings), BrowserPool(settings))
        queue = SQLiteTaskQueue(session_factory, settings)
        service = ExtractionService(queue, registry, session_factory)
        request = ExtractionRequest(
            targets=[
                TargetConfig(
                    name="broken",
                    url="https://example.com/broken",
                    retry_budget=0,
                    selectors=[SelectorSpec(name="price", css=".price", required=True)],
                )
            ]
        )
        created = await service.submit(request)
        processed = await service.process_available(limit=1, worker_id="failure-test")
        run = await service.get_run(created.run_id)

    async with session_factory() as session:
        task = (await session.scalars(select(QueueTask))).one()

    assert processed == 1
    assert run is not None
    assert run.failed_tasks == 1
    assert task.status == TaskStatus.DEAD

