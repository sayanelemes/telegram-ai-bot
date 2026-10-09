import asyncio
import pytest
from app.services.reminders import ReminderService
from app.database.models import ReminderDB


@pytest.mark.asyncio
async def test_reminder_service(user_repo, reminder_repo, mock_bot):
    user = await user_repo.get_or_create_user(telegram_id=112233, timezone="Asia/Almaty")
    service = ReminderService(reminder_repo, bot=mock_bot)

    # 1. Init default reminders
    await service.init_default_user_reminders(user.id)
    reminders = await reminder_repo.get_user_reminders(user.id)
    assert len(reminders) == 5

    # 2. Start scheduler
    service.start()
    assert service.scheduler.running is True

    # 3. Register a job
    rem = reminders[0]  # breakfast
    await service.register_job_for_user(
        user_id=user.id,
        telegram_id=user.telegram_id,
        timezone_str="Asia/Almaty",
        reminder=rem,
    )
    job_id = service._get_job_id(user.id, rem.reminder_type)
    job = service.scheduler.get_job(job_id)
    assert job is not None

    # 4. Disable reminder and re-register
    rem.is_enabled = False
    await service.register_job_for_user(
        user_id=user.id,
        telegram_id=user.telegram_id,
        timezone_str="Asia/Almaty",
        reminder=rem,
    )
    job_after = service.scheduler.get_job(job_id)
    assert job_after is None

    # 5. Shutdown scheduler
    service.shutdown()
    await asyncio.sleep(0.05)
    assert service.scheduler.running is False
