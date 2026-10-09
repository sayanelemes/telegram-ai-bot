from typing import List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import (
    get_current_user,
    get_user_repo,
    get_reminder_repo,
    get_reminder_service,
)
from app.api.schemas import (
    ReminderItemResponse,
    ReminderUpdateRequest,
    TimezoneUpdateRequest,
)
from app.database.models import UserDB
from app.database.repositories import UserRepository, ReminderRepository
from app.services import ReminderService

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=List[ReminderItemResponse])
async def get_reminders(
    user: UserDB = Depends(get_current_user),
    reminder_repo: ReminderRepository = Depends(get_reminder_repo),
    reminder_service: ReminderService = Depends(get_reminder_service),
):
    await reminder_service.init_default_user_reminders(user.id)
    reminders = await reminder_repo.get_user_reminders(user.id)

    return [
        ReminderItemResponse(
            reminder_type=r.reminder_type,
            title=ReminderService.REMINDER_TITLES.get(r.reminder_type, r.reminder_type),
            time_str=r.time_str,
            interval_hours=r.interval_hours,
            is_enabled=r.is_enabled,
        )
        for r in reminders
    ]


@router.patch("/{reminder_type}", response_model=ReminderItemResponse)
async def update_reminder(
    reminder_type: str,
    payload: ReminderUpdateRequest,
    user: UserDB = Depends(get_current_user),
    reminder_repo: ReminderRepository = Depends(get_reminder_repo),
    reminder_service: ReminderService = Depends(get_reminder_service),
):
    current = await reminder_repo.get_reminder(user.id, reminder_type)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Напоминание не найдено.")

    if payload.is_enabled is not None:
        await reminder_repo.toggle_reminder(user.id, reminder_type, payload.is_enabled)
        current.is_enabled = payload.is_enabled

    if payload.time_str is not None or payload.interval_hours is not None:
        new_time = payload.time_str if payload.time_str is not None else current.time_str
        new_interval = payload.interval_hours if payload.interval_hours is not None else current.interval_hours
        await reminder_repo.update_reminder_time(user.id, reminder_type, new_time, new_interval)
        current.time_str = new_time
        current.interval_hours = new_interval

    # Reschedule in APScheduler
    await reminder_service.register_job_for_user(
        user_id=user.id,
        telegram_id=user.telegram_id,
        timezone_str=user.timezone,
        reminder=current,
    )

    return ReminderItemResponse(
        reminder_type=current.reminder_type,
        title=ReminderService.REMINDER_TITLES.get(current.reminder_type, current.reminder_type),
        time_str=current.time_str,
        interval_hours=current.interval_hours,
        is_enabled=current.is_enabled,
    )


@router.patch("/timezone", response_model=dict)
async def update_timezone(
    payload: TimezoneUpdateRequest,
    user: UserDB = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    reminder_repo: ReminderRepository = Depends(get_reminder_repo),
    reminder_service: ReminderService = Depends(get_reminder_service),
):
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, Exception):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверное имя часового пояса.")

    await user_repo.update_timezone(user.id, payload.timezone)
    user.timezone = payload.timezone

    # Reschedule all reminders with new timezone
    user_reminders = await reminder_repo.get_user_reminders(user.id)
    for r in user_reminders:
        await reminder_service.register_job_for_user(
            user_id=user.id,
            telegram_id=user.telegram_id,
            timezone_str=payload.timezone,
            reminder=r,
        )

    return {"success": True, "timezone": payload.timezone}
