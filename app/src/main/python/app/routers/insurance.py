from typing import Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates

router = APIRouter(prefix="/insurances", tags=["insurances"])

@router.get("")
def list_insurances(request: Request, db: Session = Depends(get_db), user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant))):
    rows = db.query(models.InsuranceCompany).order_by(models.InsuranceCompany.name).all()
    return templates.TemplateResponse("insurances.html", {"request": request, "user": user, "insurances": rows})

@router.post("/new")
def create_insurance(name: str = Form(...), coverage_percent: str = Form(...), db: Session = Depends(get_db), user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant))):
    try:
        percent = max(0.0, min(100.0, float(str(coverage_percent).replace(",", "").strip())))
    except ValueError:
        percent = 0.0
    name = name.strip()
    if name and not db.query(models.InsuranceCompany).filter(models.InsuranceCompany.name == name).first():
        db.add(models.InsuranceCompany(name=name, coverage_percent=percent, is_active=True))
        db.commit()
    return RedirectResponse("/insurances", status_code=303)

@router.post("/{insurance_id}/edit")
def edit_insurance(insurance_id: int, name: str = Form(...), coverage_percent: str = Form(...), is_active: Optional[str] = Form(None), db: Session = Depends(get_db), user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant))):
    row = db.query(models.InsuranceCompany).filter(models.InsuranceCompany.id == insurance_id).first()
    if row:
        try:
            row.coverage_percent = max(0.0, min(100.0, float(str(coverage_percent).replace(",", "").strip())))
        except ValueError:
            pass
        row.name = name.strip() or row.name
        row.is_active = bool(is_active)
        db.commit()
    return RedirectResponse("/insurances", status_code=303)

@router.get("/{insurance_id}/services")
def insurance_services_form(insurance_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant))):
    insurance = db.query(models.InsuranceCompany).filter(models.InsuranceCompany.id == insurance_id).first()
    if not insurance:
        return RedirectResponse("/insurances", status_code=303)
    services = db.query(models.ServiceItem).order_by(models.ServiceItem.sort_order, models.ServiceItem.name).all()
    coverage = {x.service_item_id: x for x in insurance.service_coverages}
    rows = [{"service": s, "coverage": coverage.get(s.id)} for s in services]
    return templates.TemplateResponse("insurance_services.html", {"request": request, "user": user, "insurance": insurance, "rows": rows})

@router.post("/{insurance_id}/services")
async def save_insurance_services(insurance_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant))):
    insurance = db.query(models.InsuranceCompany).filter(models.InsuranceCompany.id == insurance_id).first()
    if not insurance:
        return RedirectResponse("/insurances", status_code=303)
    form = await request.form()
    selected_ids = {int(x) for x in form.getlist("service_id") if str(x).isdigit()}
    coverage_by_id = {}
    for sid in selected_ids:
        raw = str(form.get(f"coverage_{sid}") or "0").replace(",", "").strip()
        try:
            coverage_by_id[sid] = max(0.0, min(100.0, float(raw)))
        except ValueError:
            coverage_by_id[sid] = 0.0

    existing = {x.service_item_id: x for x in insurance.service_coverages}
    for sid, row in existing.items():
        if sid not in selected_ids:
            db.delete(row)
        else:
            row.coverage_percent = coverage_by_id.get(sid, 0)
            row.is_active = True
    for sid in selected_ids:
        if sid not in existing:
            db.add(models.InsuranceServiceCoverage(insurance_id=insurance.id, service_item_id=sid, coverage_percent=coverage_by_id.get(sid, 0), is_active=True))
    db.commit()
    return RedirectResponse(f"/insurances/{insurance_id}/services", status_code=303)
