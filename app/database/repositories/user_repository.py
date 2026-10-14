from datetime import datetime
from typing import Optional
from app.database.connection import DatabaseManager
from app.database.models import UserDB, UserProfileDB, CalorieGoalDB


class UserRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        timezone: str = "Asia/Almaty"
    ) -> UserDB:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, telegram_id, username, first_name, timezone, created_at, updated_at "
                "FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            row = await cursor.fetchone()
            now = datetime.utcnow().isoformat()
            if row:
                user = UserDB(
                    id=row["id"],
                    telegram_id=row["telegram_id"],
                    username=username or row["username"],
                    first_name=first_name or row["first_name"],
                    timezone=row["timezone"],
                    created_at=row["created_at"],
                    updated_at=now
                )
                await conn.execute(
                    "UPDATE users SET username = ?, first_name = ?, updated_at = ? WHERE id = ?",
                    (user.username, user.first_name, now, user.id)
                )
                await conn.commit()
                return user
            else:
                cursor = await conn.execute(
                    "INSERT INTO users (telegram_id, username, first_name, timezone, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (telegram_id, username, first_name, timezone, now, now)
                )
                await conn.commit()
                user_id = cursor.lastrowid
                return UserDB(
                    id=user_id,
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    timezone=timezone,
                    created_at=now,
                    updated_at=now
                )

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[UserDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, telegram_id, username, first_name, timezone, created_at, updated_at "
                "FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return UserDB(**dict(row))

    async def get_by_id(self, user_id: int) -> Optional[UserDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, telegram_id, username, first_name, timezone, created_at, updated_at "
                "FROM users WHERE id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return UserDB(**dict(row))

    async def update_timezone(self, user_id: int, timezone: str) -> None:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE users SET timezone = ?, updated_at = ? WHERE id = ?",
                (timezone, now, user_id)
            )
            await conn.commit()

    async def get_profile(self, user_id: int) -> Optional[UserProfileDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, gender, age, height_cm, weight_kg, activity_level, goal, created_at, updated_at "
                "FROM user_profiles WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return UserProfileDB(**dict(row))

    async def save_profile(self, profile: UserProfileDB) -> UserProfileDB:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO user_profiles (user_id, gender, age, height_cm, weight_kg, activity_level, goal, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "gender = excluded.gender, "
                "age = excluded.age, "
                "height_cm = excluded.height_cm, "
                "weight_kg = excluded.weight_kg, "
                "activity_level = excluded.activity_level, "
                "goal = excluded.goal, "
                "updated_at = excluded.updated_at",
                (
                    profile.user_id,
                    profile.gender,
                    profile.age,
                    profile.height_cm,
                    profile.weight_kg,
                    profile.activity_level,
                    profile.goal,
                    profile.created_at or now,
                    now,
                )
            )
            await conn.commit()
            if not profile.id:
                profile.id = cursor.lastrowid
            profile.updated_at = now
            return profile

    async def get_calorie_goal(self, user_id: int) -> Optional[CalorieGoalDB]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, bmr, tdee, target_calories, target_protein_g, target_fat_g, target_carbs_g, updated_at "
                "FROM calorie_goals WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return CalorieGoalDB(**dict(row))

    async def save_calorie_goal(self, goal: CalorieGoalDB) -> CalorieGoalDB:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO calorie_goals (user_id, bmr, tdee, target_calories, target_protein_g, target_fat_g, target_carbs_g, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "bmr = excluded.bmr, "
                "tdee = excluded.tdee, "
                "target_calories = excluded.target_calories, "
                "target_protein_g = excluded.target_protein_g, "
                "target_fat_g = excluded.target_fat_g, "
                "target_carbs_g = excluded.target_carbs_g, "
                "updated_at = excluded.updated_at",
                (
                    goal.user_id,
                    goal.bmr,
                    goal.tdee,
                    goal.target_calories,
                    goal.target_protein_g,
                    goal.target_fat_g,
                    goal.target_carbs_g,
                    now,
                )
            )
            await conn.commit()
            if not goal.id:
                goal.id = cursor.lastrowid
            goal.updated_at = now
            return goal
