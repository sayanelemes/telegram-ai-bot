from fastapi import APIRouter
from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.food import router as food_router
from app.api.routes.history import router as history_router
from app.api.routes.expenses import router as expenses_router
from app.api.routes.profile import router as profile_router
from app.api.routes.reminders import router as reminders_router
from app.api.routes.input import router as input_router
from app.api.routes.health import router as health_router
from app.api.routes.pantry import router as pantry_router
from app.api.routes.supplements import router as supplements_router
from app.api.routes.stats import router as stats_router
from app.api.routes.recipes import router as recipes_router
from app.api.routes.shopping import router as shopping_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.notes import router as notes_router
from app.api.routes.habits import router as habits_router
from app.api.routes.checkins import router as checkins_router
from app.api.routes.modes import router as modes_router
from app.api.routes.workouts import router as workouts_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(food_router)
api_router.include_router(history_router)
api_router.include_router(expenses_router)
api_router.include_router(profile_router)
api_router.include_router(reminders_router)
api_router.include_router(input_router)
api_router.include_router(health_router)
api_router.include_router(pantry_router)
api_router.include_router(supplements_router)
api_router.include_router(stats_router)
api_router.include_router(recipes_router)
api_router.include_router(shopping_router)
api_router.include_router(tasks_router)
api_router.include_router(notes_router)
api_router.include_router(habits_router)
api_router.include_router(checkins_router)
api_router.include_router(modes_router)
api_router.include_router(workouts_router)

__all__ = ["api_router"]
