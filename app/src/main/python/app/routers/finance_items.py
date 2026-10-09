from typing import Optional, List
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import require_roles
from app.templating import templates

# مدیریت جدول مستقل «آیتم‌های مالی» (نوار قلب، اکو قلب و ...)
# این آیتم‌ها در کد Hard-Code نشده‌اند و از همین صفحه قابل افزودن/ویرایش/غیرفعال‌سازی هستند.
router = APIRouter(prefix="/finance/items", tags=["finance-items"])


def _to_number(value) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    cleaned = str(value).replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


@router.get("")
def list_service_items(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    items = db.query(models.ServiceItem).order_by(
        models.ServiceItem.sort_order, models.ServiceItem.name
    ).all()
    return templates.TemplateResponse(
        "finance_items.html", {"request": request, "user": user, "items": items}
    )


@router.get("/prices")
def prices_form(
    request: Request,
    saved: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    items = db.query(models.ServiceItem).order_by(
        models.ServiceItem.sort_order, models.ServiceItem.name
    ).all()
    return templates.TemplateResponse(
        "finance_prices.html",
        {"request": request, "user": user, "items": items, "saved": bool(saved)},
    )


@router.post("/prices")
def prices_save(
    item_ids: List[int] = Form([]),
    prices: List[str] = Form([]),
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    for item_id, price in zip(item_ids, prices):
        item = db.query(models.ServiceItem).filter(models.ServiceItem.id == item_id).first()
        if item:
            item.default_price = _to_number(price)
    db.commit()
    return RedirectResponse("/finance/items/prices?saved=1", status_code=303)


@router.get("/new")
def new_service_item_form(
    request: Request,
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    return templates.TemplateResponse(
        "finance_item_form.html", {"request": request, "user": user, "item": None}
    )


@router.post("/new")
def create_service_item(
    name: str = Form(...),
    default_price: Optional[str] = Form(None),
    sort_order: Optional[str] = Form("0"),
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    item = models.ServiceItem(
        name=name.strip(),
        default_price=_to_number(default_price),
        sort_order=int(sort_order or 0),
        is_active=True,
    )
    db.add(item)
    db.commit()
    return RedirectResponse("/finance/items", status_code=303)


@router.get("/{item_id}/edit")
def edit_service_item_form(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    item = db.query(models.ServiceItem).filter(models.ServiceItem.id == item_id).first()
    if not item:
        return RedirectResponse("/finance/items", status_code=303)
    return templates.TemplateResponse(
        "finance_item_form.html", {"request": request, "user": user, "item": item}
    )


@router.post("/{item_id}/edit")
def update_service_item(
    item_id: int,
    name: str = Form(...),
    default_price: Optional[str] = Form(None),
    sort_order: Optional[str] = Form("0"),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    item = db.query(models.ServiceItem).filter(models.ServiceItem.id == item_id).first()
    if not item:
        return RedirectResponse("/finance/items", status_code=303)
    item.name = name.strip()
    item.default_price = _to_number(default_price)
    item.sort_order = int(sort_order or 0)
    item.is_active = bool(is_active)
    db.commit()
    return RedirectResponse("/finance/items", status_code=303)


@router.post("/{item_id}/delete")
def delete_service_item(
    item_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin, models.UserRole.accountant)),
):
    item = db.query(models.ServiceItem).filter(models.ServiceItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse("/finance/items", status_code=303)
