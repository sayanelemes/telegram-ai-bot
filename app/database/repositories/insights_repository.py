import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from app.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class InsightsRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    # ==========================
    # FINDINGS
    # ==========================

    async def save_finding(
        self,
        user_id: int,
        finding_type: str,
        severity: str,
        evidence: Dict[str, Any],
        suggested_action: Optional[str] = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        evidence_str = json.dumps(evidence, ensure_ascii=False)
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO insights_findings (user_id, finding_type, severity, evidence_json, suggested_action, detected_at) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                (user_id, finding_type, severity, evidence_str, suggested_action, now)
            )
            finding_id = cur.lastrowid
            await conn.commit()
            return finding_id

    async def get_latest_findings(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM insights_findings WHERE user_id = ? ORDER BY id DESC LIMIT ?;",
                (user_id, limit)
            )
            rows = await cur.fetchall()
            findings = []
            for r in rows:
                item = dict(r)
                try:
                    item["evidence"] = json.loads(item["evidence_json"])
                except Exception:
                    item["evidence"] = {}
                findings.append(item)
            return findings

    async def clear_old_findings(self, user_id: int) -> int:
        async with self.db.get_connection() as conn:
            cur = await conn.execute("DELETE FROM insights_findings WHERE user_id = ?;", (user_id,))
            await conn.commit()
            return cur.rowcount

    # ==========================
    # DATA READINESS CHECK (14 DAYS)
    # ==========================

    async def get_distinct_log_days_count(self, user_id: int) -> int:
        """Count distinct dates across food_entries, weight_logs, and workout_logs."""
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT COUNT(DISTINCT log_date) as day_count FROM (
                    SELECT entry_date as log_date FROM food_entries WHERE user_id = ?
                    UNION
                    SELECT log_date FROM weight_logs WHERE user_id = ?
                    UNION
                    SELECT workout_date as log_date FROM workout_logs WHERE user_id = ?
                )
                """,
                (user_id, user_id, user_id)
            )
            row = await cur.fetchone()
            return int(row["day_count"]) if row else 0

    # ==========================
    # AI ADVICE
    # ==========================

    async def save_ai_advice(
        self,
        user_id: int,
        week_start: str,
        advice_payload: Dict[str, Any],
    ) -> int:
        now = datetime.utcnow().isoformat()
        advice_str = json.dumps(advice_payload, ensure_ascii=False)
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO ai_advice (user_id, week_start, advice_json, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?);",
                (user_id, week_start, advice_str, now)
            )
            advice_id = cur.lastrowid
            await conn.commit()
            return advice_id

    async def get_latest_ai_advice(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM ai_advice WHERE user_id = ? ORDER BY id DESC LIMIT 1;",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["advice"] = json.loads(item["advice_json"])
            except Exception:
                item["advice"] = {}
            return item

    async def get_ai_advice_by_id(self, user_id: int, advice_id: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM ai_advice WHERE id = ? AND user_id = ?;",
                (advice_id, user_id)
            )
            row = await cur.fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["advice"] = json.loads(item["advice_json"])
            except Exception:
                item["advice"] = {}
            return item

    async def mark_advice_applied(
        self,
        user_id: int,
        advice_id: int,
        applied_card_index: int,
        undo_payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = datetime.utcnow().isoformat()
        item = await self.get_ai_advice_by_id(user_id, advice_id)
        if not item:
            return False

        advice_data = item.get("advice", {})
        advice_data["applied_card_index"] = applied_card_index
        advice_data["undo_payload"] = undo_payload or {}
        advice_str = json.dumps(advice_data, ensure_ascii=False)

        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "UPDATE ai_advice SET status = 'applied', applied_at = ?, advice_json = ? WHERE id = ? AND user_id = ?;",
                (now, advice_str, advice_id, user_id)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def mark_advice_undone(self, user_id: int, advice_id: int) -> bool:
        item = await self.get_ai_advice_by_id(user_id, advice_id)
        if not item:
            return False

        advice_data = item.get("advice", {})
        advice_data.pop("undo_payload", None)
        advice_data.pop("applied_card_index", None)
        advice_str = json.dumps(advice_data, ensure_ascii=False)

        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "UPDATE ai_advice SET status = 'pending', applied_at = NULL, advice_json = ? WHERE id = ? AND user_id = ?;",
                (advice_str, advice_id, user_id)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def mark_advice_effect(self, advice_id: int, effect_result: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "UPDATE ai_advice SET effect_checked_at = ?, effect_result = ? WHERE id = ?;",
                (now, effect_result, advice_id)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def get_advices_needing_effect_check(self, days_since_applied: int = 14) -> List[Dict[str, Any]]:
        cutoff_date = (datetime.utcnow() - timedelta(days=days_since_applied)).isoformat()
        async with self.db.get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM ai_advice WHERE status = 'applied' AND effect_checked_at IS NULL AND applied_at <= ?;",
                (cutoff_date,)
            )
            rows = await cur.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["advice"] = json.loads(item["advice_json"])
                except Exception:
                    item["advice"] = {}
                results.append(item)
            return results
