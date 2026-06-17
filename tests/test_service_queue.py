from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from price_intel.orm import ExtractedItem, QueueTask
from price_intel.schemas import ExtractionRequest, SelectorSpec, TargetConfig, TaskStatus
from price_intel.service import ExtractionService


def request_payload() -> ExtractionRequest:
    return ExtractionRequest(
        metadata={"test": True},
        targets=[
            TargetConfig(
                name="demo",
                url="https://example.com/demo",
                selectors=[
                    SelectorSpec(name="price", css="h1", required=True),
                    SelectorSpec(name="cta", css="a", attr="href"),
                ],
            )
        ],
    )


async def test_service_creates_run_and_processes_task(
    extraction_service: ExtractionService,
    session_factory: async_sessionmaker,
) -> None:
    created = await extraction_service.submit(request_payload())

    processed = await extraction_service.process_available(limit=5, worker_id="test-worker")
    run = await extraction_service.get_run(created.run_id)
    items = await extraction_service.list_items(created.run_id)

    assert processed == 1
    assert run is not None
    assert run.completed_tasks == 1
    assert run.failed_tasks == 0
    assert items[0].values["price"] == "$12.50"

    async with session_factory() as session:
        task = (await session.scalars(select(QueueTask))).one()
        item = (await session.scalars(select(ExtractedItem))).one()

    assert task.status == TaskStatus.SUCCEEDED
    assert item.success is True

