from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from price_intel.orm import ExtractionRun, QueueTask, utc_now
from price_intel.schemas import RunStatus, TargetConfig, TaskStatus
from price_intel.settings import Settings


class SQLiteTaskQueue:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Settings):
        self._session_factory = session_factory
        self._settings = settings

    async def create_run(
        self,
        targets: list[TargetConfig],
        metadata: dict[str, object],
    ) -> ExtractionRun:
        async with self._session_factory() as session:
            run = ExtractionRun(
                status=RunStatus.QUEUED,
                total_tasks=len(targets),
                run_metadata=metadata,
            )
            session.add(run)
            await session.flush()
            for target in targets:
                session.add(
                    QueueTask(
                        run_id=run.run_id,
                        target=target.model_dump(mode="json"),
                        retry_budget=target.retry_budget
                        if target.retry_budget is not None
                        else self._settings.default_retry_budget,
                    )
                )
            await session.commit()
            await session.refresh(run)
            return run

    async def lease(self, worker_id: str, limit: int = 10) -> list[QueueTask]:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            query: Select[tuple[QueueTask]] = (
                select(QueueTask)
                .where(
                    (QueueTask.status == TaskStatus.PENDING)
                    | (
                        (QueueTask.status == TaskStatus.LEASED)
                        & (QueueTask.leased_until.is_not(None))
                        & (QueueTask.leased_until < now)
                    )
                )
                .order_by(QueueTask.created_at.asc())
                .limit(limit)
            )
            tasks = list((await session.scalars(query)).all())
            for task in tasks:
                task.status = TaskStatus.LEASED
                task.locked_by = worker_id
                task.leased_until = now + timedelta(seconds=self._settings.task_lease_seconds)
                task.updated_at = now
                run = await session.get(ExtractionRun, task.run_id)
                if run and run.status == RunStatus.QUEUED:
                    run.status = RunStatus.RUNNING
                    run.updated_at = now
            await session.commit()
            for task in tasks:
                await session.refresh(task)
            return tasks

    async def mark_succeeded(self, task_id: int) -> None:
        async with self._session_factory() as session:
            task = await session.get(QueueTask, task_id)
            if task is None:
                return
            task.status = TaskStatus.SUCCEEDED
            task.updated_at = utc_now()
            task.leased_until = None
            await self._refresh_run(session, task.run_id)
            await session.commit()

    async def mark_failed(self, task_id: int, error: str) -> None:
        async with self._session_factory() as session:
            task = await session.get(QueueTask, task_id)
            if task is None:
                return
            task.attempts += 1
            task.last_error = error
            task.updated_at = utc_now()
            task.leased_until = None
            task.status = (
                TaskStatus.PENDING if task.attempts <= task.retry_budget else TaskStatus.DEAD
            )
            await self._refresh_run(session, task.run_id)
            await session.commit()

    async def _refresh_run(self, session: AsyncSession, run_id: UUID) -> None:
        run = await session.get(ExtractionRun, run_id)
        if run is None:
            return
        tasks = list(
            (await session.scalars(select(QueueTask).where(QueueTask.run_id == run_id))).all()
        )
        run.completed_tasks = sum(task.status == TaskStatus.SUCCEEDED for task in tasks)
        run.failed_tasks = sum(
            task.status in {TaskStatus.FAILED, TaskStatus.DEAD} for task in tasks
        )
        terminal = all(task.status in {TaskStatus.SUCCEEDED, TaskStatus.DEAD} for task in tasks)
        if terminal:
            if run.failed_tasks == 0:
                run.status = RunStatus.SUCCEEDED
            elif run.completed_tasks > 0:
                run.status = RunStatus.PARTIAL
            else:
                run.status = RunStatus.FAILED
        elif any(task.status == TaskStatus.LEASED for task in tasks):
            run.status = RunStatus.RUNNING
        run.updated_at = utc_now()
