import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_productivity_repo
from app.database.models import UserDB
from app.database.repositories.productivity_repository import ProductivityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


class TaskCreateRequest(BaseModel):
    title: str
    due_at: Optional[str] = None
    priority: str = "normal"  # high, normal, low
    repeat: str = "none"


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    due_at: Optional[str] = None
    priority: Optional[str] = None
    is_completed: Optional[bool] = None


class TaskPostponeRequest(BaseModel):
    choice: str  # "tomorrow", "evening", "saturday"


@router.get("", response_model=List[Dict[str, Any]])
async def get_tasks(
    is_completed: Optional[bool] = Query(None),
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """List tasks filtered by completion status."""
    return await repo.get_tasks(user_id=current_user.id, is_completed=is_completed)


@router.post("", response_model=Dict[str, Any])
async def create_task(
    payload: TaskCreateRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Create a new task."""
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    return await repo.create_task(
        user_id=current_user.id,
        title=payload.title,
        due_at=payload.due_at,
        priority=payload.priority,
        repeat=payload.repeat,
    )


@router.patch("/{task_id}", response_model=Dict[str, Any])
async def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Update task title, due_at, priority or completion status."""
    updated = await repo.update_task(
        user_id=current_user.id,
        task_id=task_id,
        title=payload.title,
        due_at=payload.due_at,
        priority=payload.priority,
        is_completed=payload.is_completed,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@router.post("/{task_id}/postpone", response_model=Dict[str, Any])
async def postpone_task(
    task_id: int,
    payload: TaskPostponeRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """
    1-tap postpone: 'tomorrow', 'evening', 'saturday'.
    Increments postponed_count. If count >= 3, returns warning banner.
    """
    valid_choices = ("tomorrow", "evening", "saturday")
    if payload.choice not in valid_choices:
        raise HTTPException(status_code=400, detail=f"Invalid choice. Choose from {valid_choices}")

    result = await repo.postpone_task(
        user_id=current_user.id,
        task_id=task_id,
        choice=payload.choice,
        user_timezone=current_user.timezone or "Asia/Almaty",
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Delete task."""
    deleted = await repo.delete_task(user_id=current_user.id, task_id=task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "deleted_id": task_id}
