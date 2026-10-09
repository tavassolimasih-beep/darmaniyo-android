import logging
import traceback
from urllib.parse import quote
from typing import List, Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates
from app.insurance_gateway.service import submit_prescription

logger = logging.getLogger("darmaniyo.prescriptions")
router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])
DOCTOR_ROLES = (models.UserRole.admin, models.UserRole.doctor)

@router.get("/appointment/{appointment_id}")
def prescription_page(appointment_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES))):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        return RedirectResponse("/appointments", status_code=303)
    providers = db.query(models.InsuranceProvider).filter(models.InsuranceProvider.is_active == True).order_by(models.InsuranceProvider.name).all()
    drugs = db.query(models.Drug).filter(models.Drug.is_active == True).order_by(models.Drug.generic_name).all()
    prescriptions = (db.query(models.Prescription)
                     .filter(models.Prescription.patient_id == appt.patient_id)
                     .order_by(models.Prescription.created_at.desc()).limit(30).all())
    return templates.TemplateResponse("prescription_form.html", {
        "request": request, "user": user, "appointment": appt, "patient": appt.patient,
        "providers": providers, "drugs": drugs, "prescriptions": prescriptions,
    })

@router.post("/appointment/{appointment_id}")
def create_prescription(
    request: Request,
    appointment_id: int,
    provider_id: Optional[str] = Form(None),
    drug_ids: List[str] = Form([]),
    drug_names: List[str] = Form([]),
    national_codes: List[str] = Form([]),
    dosages: List[str] = Form([]),
    dosage_others: List[str] = Form([]),
    frequencies: List[str] = Form([]),
    durations: List[str] = Form([]),
    routes: List[str] = Form([]),
    quantities: List[str] = Form([]),
    instructions: List[str] = Form([]),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES)),
):
    """ثبت نسخه؛ بدون تکیه بر lazy relationship و با rollback کامل در خطای DB."""
    try:
        appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
        if not appt:
            return RedirectResponse("/appointments", status_code=303)

        provider = None
        if provider_id and provider_id.strip():
            try:
                provider = db.query(models.InsuranceProvider).filter(
                    models.InsuranceProvider.id == int(provider_id.strip())
                ).first()
            except (TypeError, ValueError):
                provider = None

        # فقط داروهایی که واقعاً در فرم انتخاب/وارد شده‌اند ثبت شوند.
        rows = []
        n = max(len(drug_ids), len(drug_names))
        for i in range(n):
            name = (drug_names[i] if i < len(drug_names) else '').strip()
            did_raw = (drug_ids[i] if i < len(drug_ids) else '').strip()
            d = None
            if did_raw:
                try:
                    d = db.query(models.Drug).filter(models.Drug.id == int(did_raw)).first()
                except (TypeError, ValueError):
                    d = None
            if not name and d:
                name = (d.generic_name or '').strip()
            if not name:
                continue

            qraw = (quantities[i] if i < len(quantities) else '').strip()
            try:
                quantity = int(qraw) if qraw else None
            except (TypeError, ValueError):
                quantity = None

            dosage = (dosages[i] if i < len(dosages) else '').strip()
            if dosage == '__other__':
                dosage = (dosage_others[i] if i < len(dosage_others) else '').strip()

            rows.append(models.PrescriptionItem(
                drug_id=d.id if d else None,
                drug_name=name,
                national_drug_code=(national_codes[i] if i < len(national_codes) else '').strip() or (d.national_drug_code if d else None),
                dosage=dosage or None,
                frequency=(frequencies[i] if i < len(frequencies) else '').strip() or None,
                duration=(durations[i] if i < len(durations) else '').strip() or None,
                route=(routes[i] if i < len(routes) else '').strip() or None,
                quantity=quantity,
                instructions=(instructions[i] if i < len(instructions) else '').strip() or None,
            ))

        if not rows:
            return RedirectResponse(f"/prescriptions/appointment/{appointment_id}?error=لطفاً حداقل یک دارو انتخاب کنید", status_code=303)

        prescription = models.Prescription(
            patient_id=appt.patient_id,
            doctor_id=user.id,
            appointment_id=appt.id,
            provider_id=provider.id if provider else None,
            status=models.PrescriptionStatus.pending if provider else models.PrescriptionStatus.draft,
            notes=(notes or '').strip() or None,
        )
        db.add(prescription)
        db.flush()

        # ثبت مستقیم آیتم‌ها؛ از lazy-loading رابطه Prescription.items جلوگیری می‌شود.
        for item in rows:
            item.prescription_id = prescription.id
            db.add(item)

        db.flush()
        db.commit()
        return RedirectResponse(f"/prescriptions/view/{prescription.id}", status_code=303)

    except SQLAlchemyError as exc:
        db.rollback()
        # traceback کامل در ترمینال چاپ می‌شود تا علت واقعی دیده شود
        logger.error("Prescription save failed:\n%s", traceback.format_exc())
        print("=== PRESCRIPTION SAVE ERROR ===")
        traceback.print_exc()
        msg = "ثبت نسخه در پایگاه داده انجام نشد"
        if getattr(user, "role", None) == models.UserRole.admin:
            detail = str(getattr(exc, "orig", None) or exc).replace("\n", " ")[:300]
            msg += " | " + detail
        return RedirectResponse(
            f"/prescriptions/appointment/{appointment_id}?error={quote(msg)}",
            status_code=303,
        )
    except Exception as exc:
        db.rollback()
        logger.error("Prescription unexpected error:\n%s", traceback.format_exc())
        print("=== PRESCRIPTION UNEXPECTED ERROR ===")
        traceback.print_exc()
        msg = "خطای غیرمنتظره هنگام ثبت نسخه"
        if getattr(user, "role", None) == models.UserRole.admin:
            msg += " | " + f"{type(exc).__name__}: {exc}"[:300]
        return RedirectResponse(
            f"/prescriptions/appointment/{appointment_id}?error={quote(msg)}",
            status_code=303,
        )

@router.get("/view/{prescription_id}")
def prescription_detail(prescription_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES))):
    p = db.query(models.Prescription).filter(models.Prescription.id == prescription_id).first()
    if not p:
        return RedirectResponse("/appointments", status_code=303)
    return templates.TemplateResponse("prescription_detail.html", {"request": request, "user": user, "prescription": p})


@router.get("/{prescription_id}/print")
def prescription_print(prescription_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES))):
    """صفحه چاپ نسخه — کد پیگیری فعلاً خالی است و پس از اتصال API پر می‌شود."""
    p = db.query(models.Prescription).filter(models.Prescription.id == prescription_id).first()
    if not p:
        return RedirectResponse("/appointments", status_code=303)
    return templates.TemplateResponse("prescription_print.html", {"request": request, "user": user, "prescription": p})


@router.post("/{prescription_id}/submit")
def submit(prescription_id: int, db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES))):
    p = db.query(models.Prescription).filter(models.Prescription.id == prescription_id).first()
    if not p:
        return RedirectResponse("/appointments", status_code=303)
    submit_prescription(db, p)
    return RedirectResponse(f"/prescriptions/view/{prescription_id}", status_code=303)

@router.get("/drugs")
def drugs(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES))):
    rows = db.query(models.Drug).order_by(models.Drug.generic_name).all()
    return templates.TemplateResponse("prescription_drugs.html", {"request": request, "user": user, "drugs": rows})

@router.post("/drugs")
def add_drug(
    generic_name: str = Form(...), national_drug_code: Optional[str] = Form(None), brand_name: Optional[str] = Form(None), dosage_form: Optional[str] = Form(None), strength: Optional[str] = Form(None), unit: Optional[str] = Form(None), manufacturer: Optional[str] = Form(None),
    db: Session = Depends(get_db), user=Depends(require_roles(*DOCTOR_ROLES)),
):
    row = models.Drug(generic_name=generic_name.strip(), national_drug_code=(national_drug_code or '').strip() or None, brand_name=(brand_name or '').strip() or None, dosage_form=(dosage_form or '').strip() or None, strength=(strength or '').strip() or None, unit=(unit or '').strip() or None, manufacturer=(manufacturer or '').strip() or None, is_active=True)
    db.add(row); db.commit()
    return RedirectResponse("/prescriptions/drugs", status_code=303)
