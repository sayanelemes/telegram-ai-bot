import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_productivity_repo
from app.database.models import UserDB
from app.database.repositories.productivity_repository import ProductivityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["Notes"])


class NoteCreateRequest(BaseModel):
    title: Optional[str] = None
    content: str
    tags: Optional[str] = None
    is_pinned: bool = False


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None
    is_pinned: Optional[bool] = None


@router.get("", response_model=List[Dict[str, Any]])
async def get_notes(
    query: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """List notes with optional search query and tag filtering (pinned first)."""
    return await repo.get_notes(user_id=current_user.id, query=query, tag=tag)


@router.post("", response_model=Dict[str, Any])
async def create_note(
    payload: NoteCreateRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Create a new note."""
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    return await repo.create_note(
        user_id=current_user.id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        is_pinned=payload.is_pinned,
    )


@router.patch("/{note_id}", response_model=Dict[str, Any])
async def update_note(
    note_id: int,
    payload: NoteUpdateRequest,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Update note fields."""
    updated = await repo.update_note(
        user_id=current_user.id,
        note_id=note_id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        is_pinned=payload.is_pinned,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Note not found")
    return updated


@router.post("/{note_id}/pin", response_model=Dict[str, Any])
async def toggle_pin_note(
    note_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Toggle pin status of note."""
    notes = await repo.get_notes(user_id=current_user.id)
    target = next((n for n in notes if n["id"] == note_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Note not found")

    new_pin = not target["is_pinned"]
    updated = await repo.update_note(
        user_id=current_user.id,
        note_id=note_id,
        is_pinned=new_pin,
    )
    return updated


@router.delete("/{note_id}")
async def delete_note(
    note_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: ProductivityRepository = Depends(get_productivity_repo),
):
    """Delete note."""
    deleted = await repo.delete_note(user_id=current_user.id, note_id=note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "ok", "deleted_id": note_id}
