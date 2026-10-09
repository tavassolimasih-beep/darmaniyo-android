"""تنظیمات نوبت آنلاین — قابل ویرایش توسط ادمین/منشی."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates
from app import booking_settings as bs

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/booking")
def booking_settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.secretary)),
):
    settings = bs.ensure_settings(db)
    return templates.TemplateResponse(
        "booking_settings.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "closed": bs.closed_set(settings),
            "weekday_labels": bs.WEEKDAY_LABELS,
            "saved": request.query_params.get("saved") == "1",
            "error": None,
        },
    )


@router.post("/booking")
def booking_settings_save(
    request: Request,
    morning_start: str = Form(...),
    morning_end: str = Form(...),
    evening_start: str = Form(...),
    evening_end: str = Form(...),
    slot_minutes: int = Form(...),
    days_ahead: int = Form(...),
    clinic_name: Optional[str] = Form(None),
    closed_weekdays: List[str] = Form([]),
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.secretary)),
):
    settings = bs.ensure_settings(db)

    def fail(msg: str):
        return templates.TemplateResponse(
            "booking_settings.html",
            {
                "request": request,
                "user": user,
                "settings": settings,
                "closed": {int(x) for x in closed_weekdays if str(x).isdigit()},
                "weekday_labels": bs.WEEKDAY_LABELS,
                "saved": False,
                "error": msg,
                "form": {
                    "morning_start": morning_start,
                    "morning_end": morning_end,
                    "evening_start": evening_start,
                    "evening_end": evening_end,
                    "slot_minutes": slot_minutes,
                    "days_ahead": days_ahead,
                    "clinic_name": clinic_name or "",
                },
            },
            status_code=400,
        )

    try:
        ms = bs.parse_time(morning_start)
        me = bs.parse_time(morning_end)
        es = bs.parse_time(evening_start)
        ee = bs.parse_time(evening_end)
    except ValueError:
        return fail("فرمت ساعت باید HH:MM باشد (مثال 09:00).")

    if slot_minutes < 5 or slot_minutes > 120:
        return fail("فاصله نوبت باید بین ۵ تا ۱۲۰ دقیقه باشد.")
    if days_ahead < 1 or days_ahead > 90:
        return fail("تعداد روزهای قابل رزرو باید بین ۱ تا ۹۰ باشد.")

    closed_vals = []
    for x in closed_weekdays:
        if str(x).isdigit() and 0 <= int(x) <= 6:
            closed_vals.append(str(int(x)))

    settings.morning_start = ms.strftime("%H:%M")
    settings.morning_end = me.strftime("%H:%M")
    settings.evening_start = es.strftime("%H:%M")
    settings.evening_end = ee.strftime("%H:%M")
    settings.slot_minutes = int(slot_minutes)
    settings.days_ahead = int(days_ahead)
    settings.closed_weekdays = ",".join(closed_vals) if closed_vals else ""
    settings.clinic_name = (clinic_name or "").strip() or bs.DEFAULTS["clinic_name"]
    db.commit()
    return RedirectResponse("/settings/booking?saved=1", status_code=303)
