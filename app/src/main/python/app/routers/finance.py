from typing import Optional, List
import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.security import require_roles

from app.database import get_db
from app import models
from app.security import get_current_user
from app.templating import templates

router = APIRouter(prefix="/finance", tags=["finance"])
FINANCE_REPORT_ROLES = (models.UserRole.admin, models.UserRole.doctor)


def _to_number(value) -> float:
    """تبدیل رشته‌ی عددی (که ممکن است جداکننده هزارگان داشته باشد) به float."""
    if value is None:
        return 0.0
    cleaned = str(value).replace(",", "").strip()
    return float(cleaned or 0)


def _build_service_item_context(db: Session, invoice: Optional[models.Invoice] = None):
    """لیست آیتم‌های چک‌باکسی مالی را برای فرم صورتحساب آماده می‌کند.
    اگر فاکتوری در حال ویرایش باشد، ردیف‌هایی از فاکتور که با نام یکی از آیتم‌های
    فعال مطابقت داشته باشند به‌صورت «تیک‌خورده + مبلغ ثبت‌شده» نمایش داده می‌شوند
    و بقیه‌ی ردیف‌ها (آیتم‌های آزاد/سایر) در بخش ردیف‌های دستی باقی می‌مانند."""
    service_items = (
        db.query(models.ServiceItem)
        .filter(models.ServiceItem.is_active == True)  # noqa: E712
        .order_by(models.ServiceItem.sort_order, models.ServiceItem.name)
        .all()
    )

    matched_amounts = {}
    other_items = []
    if invoice:
        service_names = {si.name for si in service_items}
        for item in invoice.items:
            if item.description in service_names and item.description not in matched_amounts:
                matched_amounts[item.description] = item.amount
            else:
                other_items.append(item)

    service_item_rows = []
    for si in service_items:
        if si.name in matched_amounts:
            service_item_rows.append(
                {"id": si.id, "name": si.name, "amount": matched_amounts[si.name], "checked": True, "price": si.default_price}
            )
        else:
            service_item_rows.append(
                {"id": si.id, "name": si.name, "amount": si.default_price, "checked": False, "price": si.default_price}
            )

    return service_item_rows, other_items


@router.get("/report")
def financial_report(
    request: Request,
    days: int = 14,
    db: Session = Depends(get_db),
    user=Depends(require_roles(*FINANCE_REPORT_ROLES)),
):
    """داشبورد درآمد روزانه؛ جزئیات هر روز فقط بعد از کلیک روی ستون همان روز نمایش داده می‌شود."""
    days = max(7, min(days, 90))
    end_date = datetime.datetime.utcnow().date()
    start_date = end_date - datetime.timedelta(days=days - 1)
    payments = (
        db.query(models.Payment)
        .filter(models.Payment.paid_at >= datetime.datetime.combine(start_date, datetime.time.min))
        .filter(models.Payment.paid_at < datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min))
        .order_by(models.Payment.paid_at.asc())
        .all()
    )
    daily = {}
    for i in range(days):
        d = start_date + datetime.timedelta(days=i)
        daily[d.isoformat()] = {"date": d.isoformat(), "label": d.strftime("%Y/%m/%d"), "total": 0, "count": 0, "details": []}
    for p in payments:
        key = p.paid_at.date().isoformat()
        if key not in daily:
            continue
        amount = float(p.amount or 0)
        daily[key]["total"] += amount
        daily[key]["count"] += 1
        daily[key]["details"].append({
            "time": p.paid_at.strftime("%H:%M"),
            "patient": p.invoice.patient.full_name if p.invoice and p.invoice.patient else "-",
            "invoice_id": p.invoice_id,
            "amount": amount,
            "method": {"cash":"نقدی", "card":"کارت بانکی", "online":"آنلاین"}.get(p.method, p.method or "-")
        })
    daily_rows = list(daily.values())
    return templates.TemplateResponse("financial_report.html", {
        "request": request, "user": user, "daily_rows": daily_rows,
        "period_days": days, "start_date": start_date, "end_date": end_date,
        "total_income": sum(x["total"] for x in daily_rows),
        "today_income": daily_rows[-1]["total"] if daily_rows else 0,
    })


@router.get("/invoices")
def list_invoices(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(models.Invoice)
    if status in models.InvoiceStatus.__members__:
        query = query.filter(models.Invoice.status == models.InvoiceStatus[status])
    invoices = query.order_by(models.Invoice.created_at.desc()).all()
    return templates.TemplateResponse(
        "finance_invoices.html",
        {"request": request, "user": user, "invoices": invoices, "status_filter": status},
    )


@router.get("/invoices/new")
def new_invoice_form(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    patient_id: Optional[int] = None,
):
    patients = db.query(models.Patient).order_by(models.Patient.full_name).all()
    service_item_rows, other_items = _build_service_item_context(db)
    return templates.TemplateResponse(
        "invoice_form.html",
        {
            "request": request,
            "user": user,
            "patients": patients,
            "preselect_patient_id": patient_id,
            "service_item_rows": service_item_rows,
            "other_items": other_items,
        },
    )


def _service_coverage_map(insurance):
    if not insurance:
        return {}
    return {x.service_item_id: min(100.0, max(0.0, float(x.coverage_percent or 0)))
            for x in insurance.service_coverages if x.is_active}

def _calculate_insurance(patient, items, total: float, discount: float):
    """محاسبه سهم بیمه برای هر خدمت؛ اگر خدمت تعریف نشده باشد از درصد کلی بیمه استفاده می‌شود."""
    base_total = max(0.0, total - discount)
    insurance = patient.insurance
    default_percent = min(100.0, max(0.0, float(insurance.coverage_percent or 0))) if insurance else 0.0
    coverage_map = _service_coverage_map(insurance)
    insurance_amount = 0.0
    for item in items:
        amount = float(item["amount"] or 0)
        percent = coverage_map.get(item.get("service_item_id"), default_percent if item.get("service_item_id") is None else 0.0)
        insurance_amount += amount * percent / 100.0
    # تخفیف به نسبت مبلغ خدمات از سهم بیمه کسر می‌شود.
    if total > 0 and discount > 0:
        insurance_amount *= base_total / total
    insurance_amount = round(insurance_amount)
    patient_payable = max(0.0, base_total - insurance_amount)
    effective_percent = round((insurance_amount / base_total * 100.0), 2) if base_total else 0.0
    return insurance, effective_percent, insurance_amount, patient_payable


@router.post("/invoices/new")
async def create_invoice(
    request: Request,
    patient_id: int = Form(...),
    discount: Optional[str] = Form("0"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """ایجاد فاکتور و تسویه کامل آن در همان لحظه ثبت.

    در گردش کار جدید، منشی خدمات را انتخاب می‌کند. اگر بیمار بیمه داشته باشد،
    سهم بیمه از مبلغ خالص کسر و فقط سهم بیمار همان لحظه پرداخت می‌شود؛
    بنابراین فاکتور از نظر سهم بیمار تسویه‌شده ثبت می‌شود.
    """
    try:
        form = await request.form()
        descriptions: List[str] = form.getlist("item_description")
        amounts: List[str] = form.getlist("item_amount")

        discount_value = _to_number(discount)
        if discount_value < 0:
            discount_value = 0.0

        patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if not patient:
            db.rollback()
            return RedirectResponse("/finance/invoices/new?error=patient", status_code=303)
        invoice = models.Invoice(
            patient_id=patient_id,
            discount=discount_value,
            insurance_id=patient.insurance_id,
            status=models.InvoiceStatus.paid,
        )
        db.add(invoice)
        db.flush()

        service_ids = form.getlist("item_service_id")
        total = 0.0
        calc_items = []
        for i, (desc, amt) in enumerate(zip(descriptions, amounts)):
            desc = str(desc or "").strip()
            if not desc or not str(amt or "").strip():
                continue
            amount_value = _to_number(amt)
            if amount_value <= 0:
                continue
            sid = None
            if i < len(service_ids) and str(service_ids[i]).isdigit():
                sid = int(service_ids[i])
            db.add(models.InvoiceItem(
                invoice_id=invoice.id, description=desc, amount=amount_value, service_item_id=sid
            ))
            calc_items.append({"amount": amount_value, "service_item_id": sid})
            total += amount_value

        net_amount = max(0.0, total - discount_value)
        if total <= 0:
            db.rollback()
            return RedirectResponse("/finance/invoices/new?error=empty", status_code=303)

        invoice.total_amount = total
        insurance, percent, insurance_amount, patient_payable = _calculate_insurance(patient, calc_items, total, discount_value)
        invoice.insurance_id = insurance.id if insurance else None
        invoice.insurance_percent = percent
        invoice.insurance_amount = insurance_amount
        invoice.patient_payable = patient_payable
        invoice.status = models.InvoiceStatus.paid
        db.add(models.Payment(invoice_id=invoice.id, amount=patient_payable, method="cash"))
        db.commit()
        return RedirectResponse(f"/finance/invoices/{invoice.id}", status_code=303)
    except Exception:
        db.rollback()
        raise


@router.get("/invoices/{invoice_id}/edit")
def edit_invoice_form(
    invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/finance/invoices", status_code=303)
    patients = db.query(models.Patient).order_by(models.Patient.full_name).all()
    service_item_rows, other_items = _build_service_item_context(db, invoice)
    # ویرایش فاکتور در همه‌ی وضعیت‌ها (از جمله تسویه‌شده) مجاز است.
    return templates.TemplateResponse(
        "invoice_form.html",
        {
            "request": request,
            "user": user,
            "patients": patients,
            "invoice": invoice,
            "preselect_patient_id": invoice.patient_id,
            "service_item_rows": service_item_rows,
            "other_items": other_items,
        },
    )


@router.post("/invoices/{invoice_id}/edit")
async def edit_invoice(
    invoice_id: int,
    request: Request,
    patient_id: int = Form(...),
    discount: Optional[str] = Form("0"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/finance/invoices", status_code=303)

    try:
        form = await request.form()
        descriptions: List[str] = form.getlist("item_description")
        amounts: List[str] = form.getlist("item_amount")

        invoice.patient_id = patient_id
        invoice.discount = max(0.0, _to_number(discount))
        patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if not patient:
            db.rollback()
            return RedirectResponse(f"/finance/invoices/{invoice_id}/edit?error=patient", status_code=303)

        for item in list(invoice.items):
            db.delete(item)
        for payment in list(invoice.payments):
            db.delete(payment)
        db.flush()

        service_ids = form.getlist("item_service_id")
        total = 0.0
        calc_items = []
        for i, (desc, amt) in enumerate(zip(descriptions, amounts)):
            desc = str(desc or "").strip()
            if not desc or not str(amt or "").strip():
                continue
            amount_value = _to_number(amt)
            if amount_value <= 0:
                continue
            sid = None
            if i < len(service_ids) and str(service_ids[i]).isdigit():
                sid = int(service_ids[i])
            db.add(models.InvoiceItem(
                invoice_id=invoice.id, description=desc, amount=amount_value, service_item_id=sid
            ))
            calc_items.append({"amount": amount_value, "service_item_id": sid})
            total += amount_value

        if total <= 0:
            db.rollback()
            return RedirectResponse(f"/finance/invoices/{invoice_id}/edit?error=empty", status_code=303)

        invoice.total_amount = total
        insurance, percent, insurance_amount, patient_payable = _calculate_insurance(patient, calc_items, total, float(invoice.discount or 0))
        invoice.insurance_id = insurance.id if insurance else None
        invoice.insurance_percent = percent
        invoice.insurance_amount = insurance_amount
        invoice.patient_payable = patient_payable
        invoice.status = models.InvoiceStatus.paid
        db.add(models.Payment(invoice_id=invoice.id, amount=patient_payable, method="cash"))
        db.commit()
        return RedirectResponse(f"/finance/invoices/{invoice.id}", status_code=303)
    except Exception:
        db.rollback()
        raise


@router.get("/invoices/{invoice_id}")
def invoice_detail(
    invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/finance/invoices", status_code=303)
    return templates.TemplateResponse(
        "invoice_detail.html", {"request": request, "user": user, "invoice": invoice}
    )


@router.get("/invoices/{invoice_id}/print")
def print_invoice(
    invoice_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/finance/invoices", status_code=303)
    return templates.TemplateResponse(
        "invoice_print.html",
        {"request": request, "user": user, "invoice": invoice},
    )


def _refresh_invoice_status(invoice: models.Invoice, db: Session):
    remaining = invoice.remaining_amount
    if remaining <= 0:
        invoice.status = models.InvoiceStatus.paid
        for item in invoice.items:
            if item.lab_test_id and item.lab_test:
                item.lab_test.workflow_status = models.TestWorkflowStatus.paid
    elif invoice.paid_amount > 0:
        invoice.status = models.InvoiceStatus.partial
    else:
        invoice.status = models.InvoiceStatus.unpaid
    db.commit()


@router.post("/invoices/{invoice_id}/payment")
def add_payment(
    invoice_id: int,
    amount: str = Form(...),
    method: str = Form("cash"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """سازگاری با لینک‌های قدیمی؛ پرداخت همیشه تا مبلغ خالص کامل می‌شود."""
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if invoice:
        try:
            remaining = max(0.0, invoice.remaining_amount)
            if remaining > 0:
                db.add(models.Payment(invoice_id=invoice.id, amount=remaining, method=method))
                invoice.status = models.InvoiceStatus.paid
                db.commit()
            return RedirectResponse(f"/finance/invoices/{invoice_id}", status_code=303)
        except Exception:
            db.rollback()
            raise
    return RedirectResponse("/finance/invoices", status_code=303)


@router.post("/invoices/{invoice_id}/delete")
def delete_invoice(
    invoice_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if invoice:
        db.delete(invoice)
        db.commit()
    return RedirectResponse("/finance/invoices", status_code=303)
