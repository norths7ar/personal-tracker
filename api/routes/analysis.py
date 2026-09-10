from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.security import require_api_auth
from services import analysis as analysis_service

router = APIRouter(
    prefix="/api/analysis",
    tags=["analysis"],
    dependencies=[Depends(require_api_auth)],
)


class BreakdownItem(BaseModel):
    category: str | None
    subcategory: str | None
    total: float
    count: int


class DailyPoint(BaseModel):
    date: str
    income: float
    expense: float


class AnalysisEntry(BaseModel):
    id: int
    date: str
    allocation_date: str
    description: str
    category: str
    subcategory: str
    amount: float
    contribution: float
    type: str
    bucket: Literal["income", "expense"]


class PeriodData(BaseModel):
    income: float
    expense: float
    balance: float
    daily: list[DailyPoint]
    expense_breakdown: list[BreakdownItem]
    income_breakdown: list[BreakdownItem]
    entries: list[AnalysisEntry] = Field(default_factory=list)


class PeriodSummary(BaseModel):
    label: str
    income: float
    expense: float


class MonthBudget(BaseModel):
    amortized_total: float | None
    cash_total: float | None


class ExpenseAnalysisResponse(BaseModel):
    months: list[str]
    years: list[str]
    selected_period: str | None
    days: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    current: PeriodData | None = None
    cash_current: PeriodData | None = None
    timeline: list[PeriodSummary] = Field(default_factory=list)
    fixed_monthly_cost: float | None = None
    budget: MonthBudget | None = None
    cash_expense: float | None = None
    amortized_expense: float | None = None


class MonthBudgetUpdate(BaseModel):
    amortized_total: float | None = Field(default=None, ge=0)
    cash_total: float | None = Field(default=None, ge=0)


@router.get("/expenses", response_model=ExpenseAnalysisResponse)
def expense_analysis(
    granularity: Literal["month", "year"] = Query(default="month"),
    period: str | None = None,
    basis: Literal["cash", "amortized"] = Query(default="amortized"),
) -> dict:
    return analysis_service.get_expense_analysis(granularity, period, basis)


@router.put("/budgets/{month}", response_model=MonthBudget)
def update_budget(month: str, body: MonthBudgetUpdate) -> dict:
    try:
        return analysis_service.update_month_budget(
            month, body.amortized_total, body.cash_total
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
