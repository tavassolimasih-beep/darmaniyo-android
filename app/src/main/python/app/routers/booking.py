"""نوبت‌دهی آنلاین عمومی — بدون نیاز به ورود."""
from __future__ import annotations

import datetime
import re
from typing import List, Optional

import jdatetime
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.templating import templates
from app import sms as sms_service
from app import booking_settings as bs

router = APIRouter(tags=["booking"])


def _parse_jalali_or_iso(value: str) -> datetime.date:
    value = (value or "").strip()
    m = re.fullmatch(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", value)
    if m:
        y, mo, d = map(int, m.groups())
        if y > 1500:
            return datetime.date(y, mo, d)
        return jdatetime.date(y, mo, d).togregorian()
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def _iter_slots_for_day(day: datetime.date, settings: models.BookingSettings) -> List[datetime.time]:
    if day.weekday() in bs.closed_set(settings):
        return []
    slots: List[datetime.time] = []
    step = max(5, int(settings.slot_minutes or 30))
    ranges = [
        (bs.parse_time(settings.morning_start), bs.parse_time(settings.morning_end)),
        (bs.parse_time(settings.evening_start), bs.parse_time(settings.evening_end)),
    ]
    for start, end in ranges:
        if start >= end:
            continue
        current = datetime.datetime.combine(day, start)
        end_dt = datetime.datetime.combine(day, end)
        while current < end_dt:
            slots.append(current.time().replace(second=0, microsecond=0))
            current += datetime.timedelta(minutes=step)
    return slots


def _booked_times(db: Session, day: datetime.date, doctor_id: Optional[int] = None) -> set:
    q = (
        db.query(models.Appointment)
        .filter(models.Appointment.appointment_date == day)
        .filter(models.Appointment.status != models.AppointmentStatus.canceled)
    )
    if doctor_id:
        q = q.filter(models.Appointment.doctor_id == doctor_id)
    return {a.appointment_time.replace(second=0, microsecond=0) for a in q.all()}


def available_slots(db: Session, day: datetime.date, settings: models.BookingSettings, doctor_id: Optional[int] = None) -> List[str]:
    booked = _booked_times(db, day, doctor_id)
    result = []
    for t in _iter_slots_for_day(day, settings):
        if t not in booked:
            result.append(t.strftime("%H:%M"))
    return result


def _allowed_dates(settings: models.BookingSettings) -> List[datetime.date]:
    today = datetime.date.today()
    closed = bs.closed_set(settings)
    ahead = max(1, int(settings.days_ahead or 21))
    dates = []
    for i in range(0, ahead + 1):
        d = today + datetime.timedelta(days=i)
        if d.weekday() not in closed:
            dates.append(d)
    return dates


@router.get("/book")
def book_page(request: Request, date: Optional[str] = None, db: Session = Depends(get_db)):
    settings = bs.ensure_settings(db)
    doctors = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.doctor, models.User.is_active == True)
        .order_by(models.User.full_name)
        .all()
    )
    allowed = _allowed_dates(settings)
    selected = allowed[0] if allowed else datetime.date.today()
    if date:
        try:
            parsed = _parse_jalali_or_iso(date)
            if parsed in allowed:
                selected = parsed
        except Exception:
            pass
    slots = available_slots(db, selected, settings)
    return templates.TemplateResponse(
        "book.html",
        {
            "request": request,
            "doctors": doctors,
            "allowed_dates": allowed,
            "selected_date": selected,
            "slots": slots,
            "clinic_name": settings.clinic_name or bs.DEFAULTS["clinic_name"],
            "error": None,
            "success": None,
        },
    )


@router.post("/book")
def book_submit(
    request: Request,
    full_name: str = Form(...),
    national_code: str = Form(...),
    phone: str = Form(...),
    appointment_date: str = Form(...),
    appointment_time: str = Form(...),
    doctor_id: Optional[str] = Form(None),
    reason: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    settings = bs.ensure_settings(db)
    doctors = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.doctor, models.User.is_active == True)
        .order_by(models.User.full_name)
        .all()
    )
    allowed = _allowed_dates(settings)
    clinic_name = settings.clinic_name or bs.DEFAULTS["clinic_name"]

    def render_error(msg: str, selected: Optional[datetime.date] = None):
        sel = selected or (allowed[0] if allowed else datetime.date.today())
        return templates.TemplateResponse(
            "book.html",
            {
                "request": request,
                "doctors": doctors,
                "allowed_dates": allowed,
                "selected_date": sel,
                "slots": available_slots(db, sel, settings),
                "clinic_name": clinic_name,
                "error": msg,
                "success": None,
                "form": {
                    "full_name": full_name,
                    "national_code": national_code,
                    "phone": phone,
                    "reason": reason or "",
                    "doctor_id": doctor_id or "",
                },
            },
            status_code=400,
        )

    full_name = (full_name or "").strip()
    national_code = (national_code or "").strip()
    phone = (phone or "").strip()
    reason = (reason or "").strip() or "نوبت آنلاین"

    if len(full_name) < 3:
        return render_error("نام و نام خانوادگی را کامل وارد کنید.")
    if not re.fullmatch(r"\d{10}", national_code):
        return render_error("کد ملی باید ۱۰ رقم باشد.")
    if not re.fullmatch(r"09\d{9}", phone.replace(" ", "").replace("-", "")):
        return render_error("شماره موبایل را به صورت 09xxxxxxxxx وارد کنید.")

    try:
        day = _parse_jalali_or_iso(appointment_date)
    except Exception:
        return render_error("تاریخ نامعتبر است.")

    if day not in allowed:
        return render_error("این تاریخ برای نوبت‌گیری در دسترس نیست.", day)

    try:
        slot = datetime.datetime.strptime(appointment_time.strip(), "%H:%M").time()
    except ValueError:
        return render_error("ساعت نامعتبر است.", day)

    free = available_slots(db, day, settings)
    if slot.strftime("%H:%M") not in free:
        return render_error("این ساعت قبلاً گرفته شده یا آزاد نیست. ساعت دیگری انتخاب کنید.", day)

    doctor = None
    if doctor_id and doctor_id.strip():
        doctor = db.query(models.User).filter(
            models.User.id == int(doctor_id),
            models.User.role == models.UserRole.doctor,
        ).first()

    patient = db.query(models.Patient).filter(models.Patient.national_code == national_code).first()
    if not patient:
        patient = models.Patient(full_name=full_name, national_code=national_code, phone=phone)
        db.add(patient)
        db.flush()
    else:
        if not patient.phone:
            patient.phone = phone
        if patient.full_name != full_name and full_name:
            patient.full_name = full_name

    appt = models.Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id if doctor else None,
        appointment_date=day,
        appointment_time=slot,
        reason=f"نوبت آنلاین — {reason}" if not reason.startswith("نوبت آنلاین") else reason,
        status=models.AppointmentStatus.pending,
        notes="ثبت از طریق صفحه نوبت آنلاین",
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    date_j = jdatetime.date.fromgregorian(date=day).strftime("%Y/%m/%d")
    time_str = slot.strftime("%H:%M")
    msg = sms_service.appointment_confirm_message(
        patient_name=patient.full_name,
        date_jalali=date_j,
        time_str=time_str,
        clinic_name=clinic_name,
    )
    sms_result = sms_service.send_sms(phone, msg)

    return templates.TemplateResponse(
        "book_success.html",
        {
            "request": request,
            "appointment": appt,
            "patient": patient,
            "date_jalali": date_j,
            "time_str": time_str,
            "clinic_name": clinic_name,
            "sms_result": sms_result,
        },
    )
