import datetime
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models
from app.security import get_current_user
from app.templating import templates

router = APIRouter(tags=["dashboard"])


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    today = datetime.date.today()

    patients_count = db.query(models.Patient).count()

    today_appointments = (
        db.query(models.Appointment)
        .filter(models.Appointment.appointment_date == today)
        .order_by(models.Appointment.appointment_time)
        .all()
    )

    pending_labs_count = (
        db.query(models.LabTest)
        .filter(models.LabTest.status == models.LabTestStatus.pending)
        .count()
    )

    unpaid_invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.status != models.InvoiceStatus.paid)
        .all()
    )
    unpaid_total = sum(inv.remaining_amount for inv in unpaid_invoices)

    recent_patients = (
        db.query(models.Patient).order_by(models.Patient.created_at.desc()).limit(5).all()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "patients_count": patients_count,
            "today_appointments": today_appointments,
            "pending_labs_count": pending_labs_count,
            "unpaid_invoices_count": len(unpaid_invoices),
            "unpaid_total": unpaid_total,
            "recent_patients": recent_patients,
            "today": today,
        },
    )
