import asyncio
import logging
from uuid import uuid4

import httpx

from price_intel.database import create_engine, create_session_factory, init_db
from price_intel.extractors import BrowserPool, ExtractorRegistry, HttpExtractor
from price_intel.logging import configure_logging
from price_intel.queue import SQLiteTaskQueue
from price_intel.service import ExtractionService
from price_intel.settings import get_settings

logger = logging.getLogger(__name__)


async def worker_loop(poll_seconds: float = 2.0, batch_size: int = 10) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    await init_db(engine)
    session_factory = create_session_factory(engine)
    async with httpx.AsyncClient() as client:
        registry = ExtractorRegistry(HttpExtractor(client, settings), BrowserPool(settings))
        queue = SQLiteTaskQueue(session_factory, settings)
        service = ExtractionService(queue, registry, session_factory)
        worker_id = f"worker-{uuid4()}"
        try:
            while True:
                processed = await service.process_available(limit=batch_size, worker_id=worker_id)
                if processed == 0:
                    await asyncio.sleep(poll_seconds)
        finally:
            await registry.stop()
            await engine.dispose()


def run() -> None:
    asyncio.run(worker_loop())


if __name__ == "__main__":
    run()

