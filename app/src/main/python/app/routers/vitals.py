import os
import uuid
import datetime
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates

# ثبت علائم حیاتی، ECG، ABI و داروهای مصرفی توسط پرستار برای یک نوبت مشخص در برنامه‌ی امروز
router = APIRouter(prefix="/appointments", tags=["vitals"])

ALLOWED_ROLES = (models.UserRole.admin, models.UserRole.nurse, models.UserRole.doctor)

UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _to_decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _to_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _build_medication_context(db: Session, vitals: Optional[models.Vitals] = None):
    """لیست چک‌باکسی داروهای فعال را برای فرم ثبت علائم حیاتی آماده می‌کند.
    داروهایی که قبلاً برای این ویزیت ثبت شده‌اند ولی در لیست فعال نیستند (یا «سایر»
    بوده‌اند) در بخش «داروهای دیگر» به‌صورت ردیف‌های آزادِ از پیش پر شده نمایش داده می‌شوند."""
    meds = (
        db.query(models.Medication)
        .filter(models.Medication.is_active == True)  # noqa: E712
        .order_by(models.Medication.sort_order, models.Medication.name)
        .all()
    )

    selected_by_med_id = {}
    extra_rows = []
    if vitals:
        active_ids = {m.id for m in meds}
        for vm in vitals.medications:
            if vm.medication_id and vm.medication_id in active_ids:
                selected_by_med_id[vm.medication_id] = vm.dose or ""
            else:
                extra_rows.append({"name": vm.medication_name, "dose": vm.dose or ""})

    med_rows = []
    for m in meds:
        checked = m.id in selected_by_med_id
        med_rows.append(
            {
                "id": m.id,
                "name": m.name,
                "dose_options": m.dose_option_list,
                "checked": checked,
                "selected_dose": selected_by_med_id.get(m.id, ""),
            }
        )
    return med_rows, extra_rows


@router.get("/{appointment_id}/vitals")
def vitals_form(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        return RedirectResponse("/appointments", status_code=303)
    med_rows, extra_rows = _build_medication_context(db, appt.vitals)
    return templates.TemplateResponse(
        "vitals_form.html",
        {
            "request": request,
            "user": user,
            "appointment": appt,
            "vitals": appt.vitals,
            "med_rows": med_rows,
            "extra_meds": extra_rows,
        },
    )


@router.post("/{appointment_id}/vitals")
async def save_vitals(
    appointment_id: int,
    request: Request,
    bp_systolic: Optional[str] = Form(None),
    bp_diastolic: Optional[str] = Form(None),
    o2_saturation: Optional[str] = Form(None),
    ecg_notes: Optional[str] = Form(None),
    patient_history: Optional[str] = Form(None),
    ecg_file: Optional[UploadFile] = File(None),
    abi_right_arm: Optional[str] = Form(None),
    abi_right_ankle: Optional[str] = Form(None),
    abi_left_arm: Optional[str] = Form(None),
    abi_left_ankle: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        return RedirectResponse("/appointments", status_code=303)

    vitals = appt.vitals
    if not vitals:
        vitals = models.Vitals(appointment_id=appt.id)
        db.add(vitals)

    vitals.bp_systolic = _to_int(bp_systolic)
    vitals.bp_diastolic = _to_int(bp_diastolic)
    vitals.o2_saturation = _to_int(o2_saturation)
    vitals.ecg_notes = ecg_notes
    vitals.patient_history = patient_history
    vitals.abi_right_arm = _to_decimal(abi_right_arm)
    vitals.abi_right_ankle = _to_decimal(abi_right_ankle)
    vitals.abi_left_arm = _to_decimal(abi_left_arm)
    vitals.abi_left_ankle = _to_decimal(abi_left_ankle)
    vitals.recorded_by_id = user.id
    vitals.updated_at = datetime.datetime.utcnow()
    if not vitals.recorded_at:
        vitals.recorded_at = datetime.datetime.utcnow()

    if ecg_file and ecg_file.filename:
        ext = os.path.splitext(ecg_file.filename)[1]
        safe_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(dest_path, "wb") as f:
            f.write(await ecg_file.read())
        vitals.ecg_file = f"/static/uploads/{safe_name}"

    db.flush()  # تا vitals.id برای ثبت داروها آماده باشد

    # جایگزینی کامل لیست داروهای این ویزیت با مقادیر تازه‌ی فرم
    form = await request.form()
    med_ids: List[str] = form.getlist("med_id")
    med_names: List[str] = form.getlist("med_name")
    med_doses: List[str] = form.getlist("med_dose")

    vitals.medications.clear()
    for mid, name, dose in zip(med_ids, med_names, med_doses):
        name = (name or "").strip()
        if not name:
            continue
        vitals.medications.append(
            models.VitalMedication(
                medication_id=int(mid) if (mid or "").strip() else None,
                medication_name=name,
                dose=(dose or "").strip() or None,
            )
        )

    db.commit()
    return RedirectResponse(f"/appointments?date={appt.appointment_date.isoformat()}", status_code=303)
