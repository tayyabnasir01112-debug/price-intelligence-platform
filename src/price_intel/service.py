import asyncio
import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from price_intel.extractors import ExtractionResult, ExtractorRegistry
from price_intel.orm import ExtractedItem, ExtractionRun
from price_intel.queue import SQLiteTaskQueue
from price_intel.schemas import ExtractionRequest, RunCreated, RunResponse, RunStatus, TargetConfig

logger = logging.getLogger(__name__)


class ExtractionService:
    def __init__(
        self,
        queue: SQLiteTaskQueue,
        registry: ExtractorRegistry,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self._queue = queue
        self._registry = registry
        self._session_factory = session_factory

    async def submit(self, request: ExtractionRequest) -> RunCreated:
        run = await self._queue.create_run(request.targets, request.metadata)
        return RunCreated(run_id=run.run_id, status=run.status, queued_tasks=run.total_tasks)

    async def process_available(self, limit: int = 10, worker_id: str | None = None) -> int:
        worker = worker_id or f"api-worker-{uuid4()}"
        tasks = await self._queue.lease(worker, limit=limit)
        if not tasks:
            return 0

        async def process_one(task_id: int, target_data: dict[str, object]) -> None:
            target = TargetConfig.model_validate(target_data)
            try:
                result = await self._execute_with_retry(target)
                await self._persist_result(task_id, result)
                if result.success:
                    await self._queue.mark_succeeded(task_id)
                else:
                    await self._queue.mark_failed(task_id, "; ".join(result.errors))
            except Exception as exc:
                logger.exception("task crashed", extra={"price_intel_task_id": task_id})
                await self._queue.mark_failed(task_id, str(exc))

        await asyncio.gather(*(process_one(task.id, task.target) for task in tasks))
        return len(tasks)

    async def _execute_with_retry(self, target: TargetConfig) -> ExtractionResult:
        extractor = self._registry.get(target.extractor)
        retry_budget = target.retry_budget if target.retry_budget is not None else 0
        attempt = 0
        while True:
            result = await extractor.extract(target)
            if result.success or attempt >= retry_budget:
                return result
            await asyncio.sleep(min(2**attempt, 30))
            attempt += 1

    async def _persist_result(self, task_id: int, result: ExtractionResult) -> None:
        async with self._session_factory() as session:
            from price_intel.orm import QueueTask

            task = await session.get(QueueTask, task_id)
            if task is None:
                return
            session.add(
                ExtractedItem(
                    run_id=task.run_id,
                    target_name=result.target_name,
                    url=result.url,
                    success=result.success,
                    values=result.values,
                    errors=result.errors,
                    raw_excerpt=result.raw_excerpt,
                )
            )
            await session.commit()

    async def get_run(self, run_id: UUID) -> RunResponse | None:
        async with self._session_factory() as session:
            run = await session.get(ExtractionRun, run_id)
            if run is None:
                return None
            return RunResponse(
                run_id=run.run_id,
                status=RunStatus(run.status),
                total_tasks=run.total_tasks,
                completed_tasks=run.completed_tasks,
                failed_tasks=run.failed_tasks,
                metadata=run.run_metadata,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )

    async def list_items(self, run_id: UUID) -> list[ExtractedItem]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(ExtractedItem)
                        .where(ExtractedItem.run_id == run_id)
                        .order_by(ExtractedItem.id.asc())
                    )
                ).all()
            )

