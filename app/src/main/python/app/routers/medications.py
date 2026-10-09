from typing import Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates

# مدیریت جدول مستقل «لیست داروها» — این داروها برای ثبت داروهای مصرفی بیمار
# در فرم علائم حیاتی (نوار پرستاری) استفاده می‌شوند و در کد Hard-Code نشده‌اند.
router = APIRouter(prefix="/medications", tags=["medications"])

ALLOWED_ROLES = (models.UserRole.admin, models.UserRole.nurse, models.UserRole.doctor)


@router.get("")
def list_medications(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    meds = db.query(models.Medication).order_by(
        models.Medication.sort_order, models.Medication.name
    ).all()
    return templates.TemplateResponse(
        "medications.html", {"request": request, "user": user, "meds": meds}
    )


@router.get("/new")
def new_medication_form(
    request: Request,
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    return templates.TemplateResponse(
        "medication_form.html", {"request": request, "user": user, "med": None}
    )


@router.post("/new")
def create_medication(
    name: str = Form(...),
    dosage_options: Optional[str] = Form(None),
    sort_order: Optional[str] = Form("0"),
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    med = models.Medication(
        name=name.strip(),
        dosage_options=(dosage_options or "").strip() or None,
        sort_order=int(sort_order or 0),
        is_active=True,
    )
    db.add(med)
    db.commit()
    return RedirectResponse("/medications", status_code=303)


@router.get("/{med_id}/edit")
def edit_medication_form(
    med_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    med = db.query(models.Medication).filter(models.Medication.id == med_id).first()
    if not med:
        return RedirectResponse("/medications", status_code=303)
    return templates.TemplateResponse(
        "medication_form.html", {"request": request, "user": user, "med": med}
    )


@router.post("/{med_id}/edit")
def update_medication(
    med_id: int,
    name: str = Form(...),
    dosage_options: Optional[str] = Form(None),
    sort_order: Optional[str] = Form("0"),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    med = db.query(models.Medication).filter(models.Medication.id == med_id).first()
    if not med:
        return RedirectResponse("/medications", status_code=303)
    med.name = name.strip()
    med.dosage_options = (dosage_options or "").strip() or None
    med.sort_order = int(sort_order or 0)
    med.is_active = bool(is_active)
    db.commit()
    return RedirectResponse("/medications", status_code=303)


@router.post("/{med_id}/delete")
def delete_medication(
    med_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*ALLOWED_ROLES)),
):
    med = db.query(models.Medication).filter(models.Medication.id == med_id).first()
    if med:
        db.delete(med)
        db.commit()
    return RedirectResponse("/medications", status_code=303)
