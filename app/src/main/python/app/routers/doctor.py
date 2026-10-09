import datetime
from typing import List
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates

router = APIRouter(prefix="/doctor", tags=["doctor"])
DOCTOR_ROLES = (models.UserRole.admin, models.UserRole.doctor)

TEST_NAMES = [
    "تست ورزش", "تست عروق", "اکو 4 بعدی", "کانتراست اکو", "اکو معمولی",
    "اکو مادرزادی", "اکو تیشو", "هالتر فشار", "بادی آنالیز",
]


def _safe_query(fn, default=None):
    """Run optional page queries without preventing the medical-record page from opening."""
    try:
        return fn()
    except Exception:
        return default if default is not None else []


@router.get("/appointments/{appointment_id}")
def doctor_visit(appointment_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES))):
    # The appointment and patient are the minimum data required to open a medical record.
    # Optional clinical/financial history is loaded independently so an old/mismatched
    # optional table cannot turn the entire page into HTTP 500.
    try:
        appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
        if not appt:
            return RedirectResponse("/appointments", status_code=303)

        patient = db.query(models.Patient).filter(models.Patient.id == appt.patient_id).first()
        if not patient:
            return RedirectResponse("/appointments", status_code=303)

        vitals = _safe_query(lambda: db.query(models.Vitals).filter(models.Vitals.appointment_id == appointment_id).first(), None)
        services = _safe_query(lambda: db.query(models.ServiceItem)
                               .filter(models.ServiceItem.is_active == True)
                               .filter(models.ServiceItem.name.in_(TEST_NAMES))
                               .order_by(models.ServiceItem.sort_order, models.ServiceItem.name).all(), [])
        current_tests = _safe_query(lambda: db.query(models.LabTest)
                                    .filter(models.LabTest.appointment_id == appointment_id)
                                    .order_by(models.LabTest.ordered_at.desc()).all(), [])
        all_tests = _safe_query(lambda: db.query(models.LabTest)
                                .filter(models.LabTest.patient_id == patient.id)
                                .order_by(models.LabTest.ordered_at.desc()).limit(100).all(), [])
        previous_tests = [t for t in all_tests if t.appointment_id != appointment_id][:30]
        previous_appointments = _safe_query(lambda: db.query(models.Appointment)
                                            .filter(models.Appointment.patient_id == patient.id)
                                            .filter(models.Appointment.id != appointment_id)
                                            .order_by(models.Appointment.appointment_date.desc(),
                                                      models.Appointment.appointment_time.desc())
                                            .limit(20).all(), [])
        prescriptions = _safe_query(lambda: db.query(models.Prescription)
                                    .filter(models.Prescription.patient_id == patient.id)
                                    .order_by(models.Prescription.created_at.desc()).limit(20).all(), [])
        invoices = _safe_query(lambda: db.query(models.Invoice)
                               .filter(models.Invoice.patient_id == patient.id)
                               .order_by(models.Invoice.created_at.desc()).limit(10).all(), [])

        return templates.TemplateResponse("doctor_visit.html", {
            "request": request,
            "user": user,
            "appointment": appt,
            "patient": patient,
            "vitals": vitals,
            "services": services,
            "current_tests": current_tests,
            "all_tests": all_tests,
            "previous_tests": previous_tests,
            "previous_appointments": previous_appointments,
            "invoices": invoices,
            "today": datetime.date.today(),
            "prescriptions": prescriptions,
            "record_error": None,
        })
    except SQLAlchemyError as exc:
        db.rollback()
        # Keep a useful error in the server console while avoiding a blank generic 500.
        print(f"[MEDICAL_RECORD_ERROR] appointment_id={appointment_id}: {exc!r}")
        return templates.TemplateResponse("doctor_visit_safe.html", {
            "request": request,
            "user": user,
            "appointment": locals().get("appt"),
            "patient": locals().get("patient"),
            "record_error": "خطا در خواندن اطلاعات پرونده از SQL Server. جزئیات خطا در پنجره اجرای برنامه ثبت شد.",
        }, status_code=200)
    except Exception as exc:
        print(f"[MEDICAL_RECORD_ERROR] appointment_id={appointment_id}: {exc!r}")
        return templates.TemplateResponse("doctor_visit_safe.html", {
            "request": request,
            "user": user,
            "appointment": locals().get("appt"),
            "patient": locals().get("patient"),
            "record_error": "خطای داخلی هنگام باز کردن پرونده پزشکی. جزئیات خطا در پنجره اجرای برنامه ثبت شد.",
        }, status_code=200)


@router.post("/appointments/{appointment_id}/tests")
def order_tests(
    appointment_id: int,
    test_ids: List[int] = Form([]),
    db: Session = Depends(get_db),
    user=Depends(require_roles(*DOCTOR_ROLES)),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        return RedirectResponse("/appointments", status_code=303)
    if test_ids:
        existing = {t.service_item_id for t in appt.patient.lab_tests if t.appointment_id == appointment_id and t.workflow_status != models.TestWorkflowStatus.canceled}
        invoice = models.Invoice(patient_id=appt.patient_id, total_amount=0, discount=0, status=models.InvoiceStatus.unpaid)
        db.add(invoice); db.flush()
        total = 0
        added = 0
        for sid in test_ids:
            if sid in existing:
                continue
            service = db.query(models.ServiceItem).filter(models.ServiceItem.id == sid, models.ServiceItem.is_active == True).first()
            if not service:
                continue
            price = service.default_price or 0
            test = models.LabTest(
                patient_id=appt.patient_id, appointment_id=appt.id, ordered_by_id=user.id,
                service_item_id=service.id, test_name=service.name, price=price,
                status=models.LabTestStatus.pending, workflow_status=models.TestWorkflowStatus.requested,
            )
            db.add(test); db.flush()
            db.add(models.InvoiceItem(invoice_id=invoice.id, description=service.name, amount=price, lab_test_id=test.id))
            total += float(price); added += 1
        if added:
            invoice.total_amount = total
            db.commit()
        else:
            db.delete(invoice); db.commit()
    return RedirectResponse(f"/doctor/appointments/{appointment_id}", status_code=303)
