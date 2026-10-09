import datetime
from collections import defaultdict

from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates

router = APIRouter(prefix="/reports", tags=["reports"])

REPORT_ROLES = (models.UserRole.admin, models.UserRole.doctor)


@router.get("/financial")
def financial_report(
    request: Request,
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    user=Depends(require_roles(*REPORT_ROLES)),
):
    """داشبورد درآمد روزانه؛ فقط برای مدیر سیستم و پزشک."""
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=days - 1)
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time.min)

    payments = (
        db.query(models.Payment)
        .filter(models.Payment.paid_at >= start_dt, models.Payment.paid_at < end_dt)
        .order_by(models.Payment.paid_at.asc())
        .all()
    )

    daily = defaultdict(float)
    for payment in payments:
        daily[payment.paid_at.date()] += float(payment.amount or 0)

    daily_rows = []
    cursor = start_date
    while cursor <= today:
        daily_rows.append({
            "date": cursor,
            "amount": daily.get(cursor, 0),
        })
        cursor += datetime.timedelta(days=1)

    total_income = sum(row["amount"] for row in daily_rows)
    today_income = daily.get(today, 0)
    paid_transactions = len(payments)
    average_income = total_income / days if days else 0
    max_income = max((row["amount"] for row in daily_rows), default=0)

    return templates.TemplateResponse(
        "financial_report.html",
        {
            "request": request,
            "user": user,
            "days": days,
            "start_date": start_date,
            "today": today,
            "daily_rows": daily_rows,
            "total_income": total_income,
            "today_income": today_income,
            "paid_transactions": paid_transactions,
            "average_income": average_income,
            "max_income": max_income,
        },
    )
