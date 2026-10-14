import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from datetime import datetime
from app.api.deps import get_current_user, get_finance_repo, get_expense_repo
from app.database.models import UserDB
from app.database.repositories.finance_repository import FinanceRepository
from app.database.repositories.expense_repository import ExpenseRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/finances", tags=["Finances"])


# --- Schemas ---

class SavingsGoalCreate(BaseModel):
    title: str
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(0.0, ge=0)
    monthly_deposit: float = Field(0.0, ge=0)
    currency: str = "₸"
    target_date: Optional[str] = None


class SavingsGoalDeposit(BaseModel):
    amount: float = Field(..., gt=0)


class SubscriptionCreate(BaseModel):
    name: str
    amount: float = Field(..., gt=0)
    next_payment_date: str
    currency: str = "₸"
    billing_cycle: str = "monthly"


class SubscriptionUpdate(BaseModel):
    next_payment_date: str


class DebtCreate(BaseModel):
    person_name: str
    amount: float = Field(..., gt=0)
    direction: str = Field(..., pattern="^(i_owe|they_owe)$")
    currency: str = "₸"
    description: Optional[str] = None


class DebtRepay(BaseModel):
    amount: float = Field(..., gt=0)


# =========================================================================
# SAVINGS GOALS
# =========================================================================

@router.get("/savings", response_model=List[Dict[str, Any]])
async def get_savings_goals(
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """List savings goals with progress bar, percent, and forecast."""
    return await repo.get_savings_goals(user_id=current_user.id)


@router.post("/savings", response_model=Dict[str, Any])
async def create_savings_goal(
    payload: SavingsGoalCreate,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Create new savings goal."""
    return await repo.create_savings_goal(
        user_id=current_user.id,
        title=payload.title,
        target_amount=payload.target_amount,
        current_amount=payload.current_amount,
        monthly_deposit=payload.monthly_deposit,
        currency=payload.currency,
        target_date=payload.target_date,
    )


@router.post("/savings/{goal_id}/deposit", response_model=Dict[str, Any])
async def deposit_savings(
    goal_id: int,
    payload: SavingsGoalDeposit,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Deposit money into a savings goal."""
    updated = await repo.deposit_to_savings_goal(
        user_id=current_user.id,
        goal_id=goal_id,
        amount=payload.amount,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    return updated


@router.delete("/savings/{goal_id}")
async def delete_savings_goal(
    goal_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Delete a savings goal."""
    deleted = await repo.delete_savings_goal(user_id=current_user.id, goal_id=goal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    return {"status": "ok", "deleted_id": goal_id}


# =========================================================================
# SUBSCRIPTIONS
# =========================================================================

@router.get("/subscriptions", response_model=List[Dict[str, Any]])
async def get_subscriptions(
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """List recurring subscriptions with due dates and due-soon flags."""
    return await repo.get_subscriptions(user_id=current_user.id)


@router.post("/subscriptions", response_model=Dict[str, Any])
async def create_subscription(
    payload: SubscriptionCreate,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Add a recurring subscription."""
    return await repo.create_subscription(
        user_id=current_user.id,
        name=payload.name,
        amount=payload.amount,
        next_payment_date=payload.next_payment_date,
        currency=payload.currency,
        billing_cycle=payload.billing_cycle,
    )


@router.patch("/subscriptions/{sub_id}", response_model=Dict[str, Any])
async def update_subscription_date(
    sub_id: int,
    payload: SubscriptionUpdate,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Update subscription next payment date."""
    updated = await repo.update_subscription_next_date(
        user_id=current_user.id,
        sub_id=sub_id,
        next_payment_date=payload.next_payment_date,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return await repo.get_subscription_by_id(user_id=current_user.id, sub_id=sub_id)


@router.delete("/subscriptions/{sub_id}")
async def delete_subscription(
    sub_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Delete a subscription."""
    deleted = await repo.delete_subscription(user_id=current_user.id, sub_id=sub_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"status": "ok", "deleted_id": sub_id}


# =========================================================================
# DEBTS
# =========================================================================

@router.get("/debts", response_model=Dict[str, Any])
async def get_debts(
    is_settled: Optional[bool] = Query(None),
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """List debts with calculated totals (I owe, They owe, Net balance)."""
    return await repo.get_debts(user_id=current_user.id, is_settled=is_settled)


@router.post("/debts", response_model=Dict[str, Any])
async def create_debt(
    payload: DebtCreate,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Create debt record ('i_owe' or 'they_owe')."""
    return await repo.create_debt(
        user_id=current_user.id,
        person_name=payload.person_name,
        amount=payload.amount,
        direction=payload.direction,
        currency=payload.currency,
        description=payload.description,
    )


@router.post("/debts/{debt_id}/repay", response_model=Dict[str, Any])
async def partial_repay_debt(
    debt_id: int,
    payload: DebtRepay,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Partially repay debt amount. Auto-settles if amount reaches 0."""
    updated = await repo.partial_repay_debt(
        user_id=current_user.id,
        debt_id=debt_id,
        repay_amount=payload.amount,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Debt not found")
    return updated


@router.post("/debts/{debt_id}/settle", response_model=Dict[str, Any])
async def settle_debt_one_tap(
    debt_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """1-tap close/settle debt."""
    settled = await repo.settle_debt_one_tap(user_id=current_user.id, debt_id=debt_id)
    if not settled:
        raise HTTPException(status_code=404, detail="Debt not found")
    return settled


@router.delete("/debts/{debt_id}")
async def delete_debt(
    debt_id: int,
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
):
    """Delete debt record."""
    deleted = await repo.delete_debt(user_id=current_user.id, debt_id=debt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Debt not found")
    return {"status": "ok", "deleted_id": debt_id}


# =========================================================================
# UNIFIED FINANCE OVERVIEW
# =========================================================================

@router.get("/overview", response_model=Dict[str, Any])
async def get_finance_overview(
    current_user: UserDB = Depends(get_current_user),
    repo: FinanceRepository = Depends(get_finance_repo),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    """
    Unified finance dashboard screen:
    - Savings goals summary
    - Subscriptions monthly burn rate
    - Debts net balance
    - Impulse budget and protein equivalents warning
    """
    savings = await repo.get_savings_goals(user_id=current_user.id)
    subscriptions = await repo.get_subscriptions(user_id=current_user.id)
    debts = await repo.get_debts(user_id=current_user.id, is_settled=False)

    today = datetime.utcnow().date()
    start_date = today.replace(day=1).isoformat()
    end_date = today.isoformat()
    impulse = await expense_repo.get_impulse_stats(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )

    total_savings_saved = sum(s["current_amount"] for s in savings)
    total_savings_target = sum(s["target_amount"] for s in savings)
    subs_monthly = sum(sub["amount"] for sub in subscriptions if sub.get("billing_cycle") == "monthly")

    return {
        "savings": {
            "goals_count": len(savings),
            "total_saved": round(total_savings_saved, 2),
            "total_target": round(total_savings_target, 2),
            "goals": savings,
        },
        "subscriptions": {
            "count": len(subscriptions),
            "monthly_burn": round(subs_monthly, 2),
            "items": subscriptions,
        },
        "debts": debts,
        "impulse": impulse,
    }
