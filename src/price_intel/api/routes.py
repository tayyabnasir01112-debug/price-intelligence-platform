from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from price_intel.schemas import (
    ExtractedItemResponse,
    ExtractionRequest,
    HealthResponse,
    RunCreated,
    RunResponse,
)
from price_intel.service import ExtractionService
from price_intel.settings import Settings

router = APIRouter()


def get_service() -> ExtractionService:
    raise RuntimeError("service dependency was not configured")


def get_engine() -> AsyncEngine:
    raise RuntimeError("engine dependency was not configured")


def get_settings_dep() -> Settings:
    raise RuntimeError("settings dependency was not configured")


@router.get("/health", response_model=HealthResponse)
async def health(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> HealthResponse:
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return HealthResponse(service=settings.app_name, status="ok", database="ok")


@router.post("/runs", response_model=RunCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    request: ExtractionRequest,
    background: BackgroundTasks,
    service: Annotated[ExtractionService, Depends(get_service)],
) -> RunCreated:
    created = await service.submit(request)
    background.add_task(service.process_available, 25)
    return created


@router.post("/workers/process", response_model=dict[str, int])
async def process_queue(
    service: Annotated[ExtractionService, Depends(get_service)],
    limit: int = 25,
) -> dict[str, int]:
    processed = await service.process_available(limit=limit)
    return {"processed": processed}


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    service: Annotated[ExtractionService, Depends(get_service)],
) -> RunResponse:
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/runs/{run_id}/items", response_model=list[ExtractedItemResponse])
async def get_items(
    run_id: UUID,
    service: Annotated[ExtractionService, Depends(get_service)],
) -> list[ExtractedItemResponse]:
    return [ExtractedItemResponse.model_validate(item) for item in await service.list_items(run_id)]

