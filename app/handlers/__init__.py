from app.handlers.start import router as start_router
from app.handlers.short_links import router as short_links_router
from app.handlers.menu import router as menu_router
from app.handlers.food import router as food_router
from app.handlers.history import router as history_router
from app.handlers.expenses import router as expenses_router
from app.handlers.reminders import router as reminders_router
from app.handlers.profile import router as profile_router

all_routers = [
    start_router,
    short_links_router,
    menu_router,
    food_router,
    history_router,
    expenses_router,
    reminders_router,
    profile_router,
]

__all__ = ["all_routers"]
