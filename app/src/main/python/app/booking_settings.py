"""خواندن و ذخیره تنظیمات نوبت آنلاین."""
from __future__ import annotations

import datetime
from typing import Dict, List, Set

from sqlalchemy.orm import Session

from app import models

DEFAULTS = {
    "morning_start": "09:00",
    "morning_end": "13:00",
    "evening_start": "16:00",
    "evening_end": "19:00",
    "slot_minutes": 30,
    "closed_weekdays": "4",
    "days_ahead": 21,
    "clinic_name": "کلینیک تخصصی اکو کاردیوگرافی پیشرفته دکتر مریم توسلی",
}

WEEKDAY_LABELS = {
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنجشنبه",
    4: "جمعه",
    5: "شنبه",
    6: "یکشنبه",
}


def ensure_settings(db: Session) -> models.BookingSettings:
    row = db.query(models.BookingSettings).order_by(models.BookingSettings.id.asc()).first()
    if row:
        return row
    row = models.BookingSettings(
        morning_start=DEFAULTS["morning_start"],
        morning_end=DEFAULTS["morning_end"],
        evening_start=DEFAULTS["evening_start"],
        evening_end=DEFAULTS["evening_end"],
        slot_minutes=DEFAULTS["slot_minutes"],
        closed_weekdays=DEFAULTS["closed_weekdays"],
        days_ahead=DEFAULTS["days_ahead"],
        clinic_name=DEFAULTS["clinic_name"],
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def parse_time(value: str) -> datetime.time:
    value = (value or "").strip()
    return datetime.datetime.strptime(value, "%H:%M").time()


def closed_set(settings: models.BookingSettings) -> Set[int]:
    result = set()
    for part in (settings.closed_weekdays or "").split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            if 0 <= n <= 6:
                result.add(n)
    return result


def settings_to_dict(settings: models.BookingSettings) -> Dict:
    return {
        "morning_start": settings.morning_start,
        "morning_end": settings.morning_end,
        "evening_start": settings.evening_start,
        "evening_end": settings.evening_end,
        "slot_minutes": settings.slot_minutes,
        "closed_weekdays": sorted(closed_set(settings)),
        "days_ahead": settings.days_ahead,
        "clinic_name": settings.clinic_name or DEFAULTS["clinic_name"],
    }
