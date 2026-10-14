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

__all__ = ["api_router"]
