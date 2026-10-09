from typing import Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import get_current_user, require_roles, hash_password
from app.templating import templates

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin)),
):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return templates.TemplateResponse("users.html", {"request": request, "user": user, "users": users})


@router.get("/new")
def new_user_form(request: Request, user=Depends(require_roles(models.UserRole.admin))):
    return templates.TemplateResponse(
        "user_form.html", {"request": request, "user": user, "edit_user": None, "roles": list(models.UserRole)}
    )


@router.post("/new")
def create_user(
    full_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin)),
):
    new_user = models.User(
        full_name=full_name,
        username=username,
        password_hash=hash_password(password),
        role=models.UserRole(role),
        phone=phone,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse("/users", status_code=303)


@router.get("/{user_id}/edit")
def edit_user_form(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin)),
):
    edit_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not edit_user:
        return RedirectResponse("/users", status_code=303)
    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": user, "edit_user": edit_user, "roles": list(models.UserRole)},
    )


@router.post("/{user_id}/edit")
def update_user(
    user_id: int,
    full_name: str = Form(...),
    role: str = Form(...),
    phone: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_roles(models.UserRole.admin)),
):
    edit_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not edit_user:
        return RedirectResponse("/users", status_code=303)
    edit_user.full_name = full_name
    edit_user.role = models.UserRole(role)
    edit_user.phone = phone
    edit_user.is_active = bool(is_active)
    if new_password:
        edit_user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/users", status_code=303)
