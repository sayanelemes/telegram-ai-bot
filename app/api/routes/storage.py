import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_db_manager
from app.database.models import UserDB
from app.database.connection import DatabaseManager
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["Storage & Cleanup"])


def get_storage_service(db_manager: DatabaseManager = Depends(get_db_manager)) -> StorageService:
    return StorageService(db_manager)


class ArchiveRequest(BaseModel):
    cutoff_days: int = Field(365, ge=30, le=1000, description="Archive detailed records older than this number of days")


@router.get("/info", response_model=Dict[str, Any])
async def get_storage_info(
    current_user: UserDB = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    """
    Get SQLite database size, free pages, table row counts, and archivable record estimates.
    """
    return await service.get_storage_stats()


@router.post("/archive", response_model=Dict[str, Any])
async def run_archive_and_vacuum(
    payload: ArchiveRequest = ArchiveRequest(),
    current_user: UserDB = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    """
    Archive records older than cutoff_days into daily_aggregates_archive, clean TTL entries, and run VACUUM.
    """
    return await service.archive_and_vacuum(cutoff_days=payload.cutoff_days)
