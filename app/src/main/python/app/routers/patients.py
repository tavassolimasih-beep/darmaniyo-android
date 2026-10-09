import datetime
import re
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, exists, case

from app.database import get_db
from app import models
from app.security import get_current_user
from app.templating import templates

router = APIRouter(prefix="/patients", tags=["patients"])


def parse_date(value: Optional[str]):
    if not value:
        return None
    value = value.strip()
    import jdatetime
    # Jalali: 1403/01/15 or 1403-01-15
    m = re.fullmatch(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", value)
    if m:
        y, mo, d = map(int, m.groups())
        if y > 1500:  # Gregorian
            try:
                return datetime.date(y, mo, d)
            except ValueError:
                return None
        try:
            return jdatetime.date(y, mo, d).togregorian()
        except ValueError:
            return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("")
def list_patients(
    request: Request,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(models.Patient)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(models.Patient.full_name.ilike(like), models.Patient.national_code.ilike(like), models.Patient.phone.ilike(like))
        )
    # سابقه بیمار را با سه EXISTS مستقل بررسی می‌کنیم.
    # نکته‌ی مهم: در SQL Server نمی‌توان یک عبارت بولی/EXISTS را مستقیماً در SELECT
    # قرار داد (خطای نحوی می‌دهد)؛ باید آن را داخل CASE WHEN ... THEN 1 ELSE 0 END
    # پیچید تا به یک مقدار عددی معتبر برای SELECT تبدیل شود. همین نبودِ CASE WHEN
    # علت خطای Internal Server Error هنگام باز کردن لیست بیماران بود.
    has_appointment = exists().where(
        models.Appointment.patient_id == models.Patient.id
    )
    has_lab_test = exists().where(
        models.LabTest.patient_id == models.Patient.id
    )
    has_invoice = exists().where(
        models.Invoice.patient_id == models.Patient.id
    )
    history_exists = has_appointment | has_lab_test | has_invoice
    has_history_column = case((history_exists, 1), else_=0).label("has_history")

    rows = (
        query.add_columns(has_history_column)
        .order_by(models.Patient.created_at.desc())
        .all()
    )
    patients = []
    for patient, has_history in rows:
        patient.has_history = bool(has_history)
        patients.append(patient)

    return templates.TemplateResponse(
        "patients_list.html", {"request": request, "user": user, "patients": patients, "q": q or ""}
    )


@router.get("/new")
def new_patient_form(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    insurances = db.query(models.InsuranceCompany).filter(models.InsuranceCompany.is_active == True).order_by(models.InsuranceCompany.name).all()
    return templates.TemplateResponse(
        "patient_form.html", {"request": request, "user": user, "patient": None, "insurances": insurances}
    )


@router.post("/new")
def create_patient(
    full_name: str = Form(...),
    national_code: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    birth_date: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    medical_notes: Optional[str] = Form(None),
    insurance_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    patient = models.Patient(
        full_name=full_name,
        national_code=national_code or None,
        phone=phone,
        birth_date=parse_date(birth_date),
        gender=gender,
        address=address,
        medical_notes=medical_notes,
        insurance_id=insurance_id or None,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return RedirectResponse(f"/patients/{patient.id}", status_code=303)


def _patient_record_context(patient, user, request):
    """جمع‌آوری داده‌های کامل پرونده بیمار برای صفحه جزئیات و چاپ."""
    appointments = sorted(
        patient.appointments,
        key=lambda a: (a.appointment_date, a.appointment_time),
        reverse=True,
    )
    lab_tests = sorted(patient.lab_tests, key=lambda t: t.ordered_at, reverse=True)
    invoices = sorted(patient.invoices, key=lambda i: i.created_at, reverse=True)

    vitals_list = []
    for a in appointments:
        if a.vitals:
            vitals_list.append({"appointment": a, "vitals": a.vitals})

    latest_vitals = vitals_list[0]["vitals"] if vitals_list else None

    total_billed = sum(float(inv.total_amount or 0) for inv in invoices)
    total_paid = sum(float(inv.paid_amount or 0) for inv in invoices)
    unpaid_total = sum(float(inv.remaining_amount) for inv in invoices)

    return {
        "request": request,
        "user": user,
        "patient": patient,
        "appointments": appointments,
        "lab_tests": lab_tests,
        "invoices": invoices,
        "vitals_list": vitals_list,
        "latest_vitals": latest_vitals,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "unpaid_total": unpaid_total,
    }


@router.get("/{patient_id}")
def patient_detail(
    patient_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        return RedirectResponse("/patients", status_code=303)
    ctx = _patient_record_context(patient, user, request)
    return templates.TemplateResponse("patient_detail.html", ctx)


@router.get("/{patient_id}/print")
def patient_print(
    patient_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    """چاپ کامل پرونده بیمار (خلاصه، علائم حیاتی، آزمایش‌ها، سوابق، مالی)."""
    import datetime as _dt
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        return RedirectResponse("/patients", status_code=303)
    ctx = _patient_record_context(patient, user, request)
    ctx["now"] = _dt.datetime.now()
    return templates.TemplateResponse("patient_print.html", ctx)


@router.get("/{patient_id}/edit")
def edit_patient_form(
    patient_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        return RedirectResponse("/patients", status_code=303)
    insurances = db.query(models.InsuranceCompany).filter(models.InsuranceCompany.is_active == True).order_by(models.InsuranceCompany.name).all()
    return templates.TemplateResponse(
        "patient_form.html", {"request": request, "user": user, "patient": patient, "insurances": insurances}
    )


@router.post("/{patient_id}/edit")
def update_patient(
    patient_id: int,
    full_name: str = Form(...),
    national_code: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    birth_date: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    medical_notes: Optional[str] = Form(None),
    insurance_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        return RedirectResponse("/patients", status_code=303)
    patient.full_name = full_name
    patient.national_code = national_code or None
    patient.phone = phone
    patient.birth_date = parse_date(birth_date)
    patient.gender = gender
    patient.address = address
    patient.medical_notes = medical_notes
    patient.insurance_id = insurance_id or None
    db.commit()
    return RedirectResponse(f"/patients/{patient.id}", status_code=303)


@router.post("/{patient_id}/delete")
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if patient:
        db.delete(patient)
        db.commit()
    return RedirectResponse("/patients", status_code=303)
