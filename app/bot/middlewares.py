import time
import logging
from typing import Callable, Dict, Any, Awaitable
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """
    In-memory rate limiting middleware.
    Limits user actions to a maximum number of requests per minute.
    """
    def __init__(self, rate_limit_per_minute: int = 20):
        self.rate_limit = rate_limit_per_minute
        self.user_requests: Dict[int, list] = defaultdict(list)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            now = time.time()
            cutoff = now - 60.0

            # Filter old timestamps
            timestamps = [t for t in self.user_requests[user_id] if t > cutoff]
            if len(timestamps) >= self.rate_limit:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                if isinstance(event, Message):
                    await event.answer("⏳ Слишком много запросов. Пожалуйста, подождите немного.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⏳ Пожалуйста, подождите перед следующим действием.", show_alert=True)
                return None

            timestamps.append(now)
            self.user_requests[user_id] = timestamps

        return await handler(event, data)


class ErrorHandlingMiddleware(BaseMiddleware):
    """
    Global exception catcher to prevent tracebacks from leaking to users.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            logger.error(f"Unhandled exception in update handler: {exc}", exc_info=True)
            if isinstance(event, Message):
                await event.answer(
                    "❌ Произошла непредвиденная ошибка при обработке запроса. "
                    "Попробуйте ещё раз позже или вернитесь в главное меню."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "❌ Ошибка при выполнении действия.",
                    show_alert=True
                )
            return None
