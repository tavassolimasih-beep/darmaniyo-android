"""منطق ثبت نسخه در سامانهٔ بیمه + ذخیرهٔ سابقه. ثبت نسخه در برنامه هرگز به‌خاطر
خطای بیمه شکست نمی‌خورد؛ خطا فقط در سابقهٔ ارسال ثبت می‌شود."""
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from .base import PrescriptionData, PrescriptionItemData, SubmitResult, FAILED, SENT
from .registry import get_gateway


def build_data(rx: models.Prescription) -> PrescriptionData:
    patient = rx.patient
    ins = patient.insurance if patient else None
    appt = rx.appointment
    visit_date = ""
    if appt and appt.appointment_date:
        try:
            import jdatetime
            visit_date = jdatetime.date.fromgregorian(date=appt.appointment_date).strftime("%Y/%m/%d")
        except Exception:
            visit_date = str(appt.appointment_date)
    return PrescriptionData(
        prescription_id=rx.id,
        patient_name=patient.full_name if patient else "",
        patient_national_code=(patient.national_code or "") if patient else "",
        insurance_name=ins.name if ins else "",
        provider_code=rx.provider_code or "",
        doctor_name=rx.doctor.full_name if rx.doctor else "",
        visit_date=visit_date,
        diagnosis=rx.diagnosis or "",
        notes=rx.notes or "",
        items=[
            PrescriptionItemData(
                name=i.medication_name,
                national_code=i.national_code or "",
                dose=i.dose or "",
                frequency=i.frequency or "",
                duration_days=i.duration_days,
                quantity=i.quantity,
                instructions=i.instructions or "",
            )
            for i in rx.items
        ],
    )


def _record(db: Session, rx, result: SubmitResult, request_json: str, user) -> models.PrescriptionSubmission:
    sub = models.PrescriptionSubmission(
        prescription_id=rx.id,
        provider_code=rx.provider_code,
        status=result.status,
        tracking_code=(result.tracking_code or None),
        message=(result.message or "")[:480] or None,
        request_payload=request_json,
        response_payload=result.response_payload,
        attempt_no=len(rx.submissions) + 1,
        created_by_id=user.id if user else None,
    )
    db.add(sub)
    db.commit()
    db.refresh(rx)
    return sub


def submit_prescription(db: Session, rx: models.Prescription, user) -> Optional[models.PrescriptionSubmission]:
    gateway = get_gateway(rx.provider_code)
    if gateway is None or not rx.items:
        return None
    data = build_data(rx)
    try:
        result = gateway.submit(data)
    except Exception as exc:  # هر خطای شبکه/وب‌سرویس
        result = SubmitResult(FAILED, message="خطا: %s" % exc)
    return _record(db, rx, result, data.to_json(), user)


def confirm_manual(db: Session, rx: models.Prescription, tracking_code: str, user):
    """پزشک اعلام می‌کند نسخه را دستی در سامانهٔ بیمه ثبت کرده است."""
    if not rx.provider_code:
        return None
    result = SubmitResult(SENT, tracking_code=tracking_code or None, message="ثبت دستی توسط پزشک")
    return _record(db, rx, result, build_data(rx).to_json(), user)
