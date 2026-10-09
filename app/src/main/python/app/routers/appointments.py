import datetime
import re
import jdatetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import get_current_user
from app.templating import templates

router = APIRouter(prefix="/appointments", tags=["appointments"])

def parse_date_str(value: str):
    """Accept Jalali (1403/01/15, 1403-01-15) or Gregorian (2024-01-15) dates."""
    value = (value or "").strip()
    m = re.fullmatch(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", value)
    if m:
        y, mo, d = map(int, m.groups())
        if y > 1500:
            return datetime.date(y, mo, d)
        return jdatetime.date(y, mo, d).togregorian()
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()



@router.post("/quick-add")
def quick_add_today(
    patient_id: int = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """دکمه‌ی «افزودن به برنامه امروز» در لیست بیماران: برای بیمار موجود، بدون نیاز به
    پر کردن فرم کامل نوبت، همین الان یک ردیف در برنامه‌ی امروز ایجاد می‌کند."""
    today = datetime.date.today()
    now_time = datetime.datetime.now().time().replace(microsecond=0)
    appt = models.Appointment(
        patient_id=patient_id,
        appointment_date=today,
        appointment_time=now_time,
        reason="ویزیت امروز",
        status=models.AppointmentStatus.pending,
    )
    db.add(appt)
    db.commit()
    return RedirectResponse(f"/appointments?date={today.isoformat()}", status_code=303)


@router.get("")
def list_appointments(
    request: Request,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if date:
        try:
            selected_date = parse_date_str(date)
        except (ValueError, TypeError):
            selected_date = datetime.date.today()
    else:
        selected_date = datetime.date.today()

    appointments = (
        db.query(models.Appointment)
        .filter(models.Appointment.appointment_date == selected_date)
        .order_by(models.Appointment.appointment_time)
        .all()
    )
    doctors = db.query(models.User).filter(models.User.role == models.UserRole.doctor).all()
    return templates.TemplateResponse(
        "appointments.html",
        {
            "request": request,
            "user": user,
            "appointments": appointments,
            "selected_date": selected_date,
            "doctors": doctors,
        },
    )


@router.get("/new")
def new_appointment_form(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    patient_id: Optional[int] = None,
):
    patients = db.query(models.Patient).order_by(models.Patient.full_name).all()
    doctors = db.query(models.User).filter(models.User.role == models.UserRole.doctor).all()
    return templates.TemplateResponse(
        "appointment_form.html",
        {
            "request": request,
            "user": user,
            "patients": patients,
            "doctors": doctors,
            "appointment": None,
            "preselect_patient_id": patient_id,
        },
    )


@router.post("/new")
def create_appointment(
    patient_id: int = Form(...),
    doctor_id: Optional[int] = Form(None),
    appointment_date: str = Form(...),
    appointment_time: str = Form(...),
    reason: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    appt = models.Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id or None,
        appointment_date=parse_date_str(appointment_date),
        appointment_time=datetime.datetime.strptime(appointment_time, "%H:%M").time(),
        reason=reason,
        notes=notes,
        status=models.AppointmentStatus.pending,
    )
    db.add(appt)
    db.commit()
    return RedirectResponse(f"/appointments?date={appt.appointment_date.isoformat()}", status_code=303)


@router.get("/{appointment_id}/edit")
def edit_appointment_form(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        return RedirectResponse("/appointments", status_code=303)
    patients = db.query(models.Patient).order_by(models.Patient.full_name).all()
    doctors = db.query(models.User).filter(models.User.role == models.UserRole.doctor).all()
    return templates.TemplateResponse(
        "appointment_form.html",
        {
            "request": request,
            "user": user,
            "patients": patients,
            "doctors": doctors,
            "appointment": appt,
            "preselect_patient_id": appt.patient_id,
        },
    )


@router.post("/{appointment_id}/edit")
def update_appointment(
    appointment_id: int,
    patient_id: int = Form(...),
    doctor_id: Optional[int] = Form(None),
    appointment_date: str = Form(...),
    appointment_time: str = Form(...),
    reason: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        return RedirectResponse("/appointments", status_code=303)

    appt.patient_id = patient_id
    appt.doctor_id = doctor_id or None
    appt.appointment_date = parse_date_str(appointment_date)
    appt.appointment_time = datetime.datetime.strptime(appointment_time, "%H:%M").time()
    appt.reason = reason
    appt.notes = notes
    db.commit()
    return RedirectResponse(f"/appointments?date={appt.appointment_date.isoformat()}", status_code=303)


@router.post("/{appointment_id}/status")
def update_status(
    appointment_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if appt and status in models.AppointmentStatus.__members__:
        appt.status = models.AppointmentStatus[status]
        db.commit()
        redirect_date = appt.appointment_date.isoformat()
    else:
        redirect_date = datetime.date.today().isoformat()
    return RedirectResponse(f"/appointments?date={redirect_date}", status_code=303)


@router.post("/{appointment_id}/delete")
def delete_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    redirect_date = datetime.date.today().isoformat()
    if appt:
        redirect_date = appt.appointment_date.isoformat()
        db.delete(appt)
        db.commit()
    return RedirectResponse(f"/appointments?date={redirect_date}", status_code=303)
