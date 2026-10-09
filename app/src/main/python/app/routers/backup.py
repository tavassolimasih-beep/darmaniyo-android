import datetime
import decimal
import enum
import json
import os
import re
import shutil
import zipfile
from typing import Optional

from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy import text

from app.database import engine, SessionLocal
from app import models
from app.security import require_roles
from app.templating import templates

# ---------------------------------------------------------------------------
# ماژول پشتیبان‌گیری (Backup)
#
# این ماژول یک بکاپ «منطقی» می‌سازد: تمام رکوردهای جدول‌ها به‌صورت JSON خوانده
# می‌شوند و به‌همراه پوشه‌ی فایل‌های آپلودشده (مدارک بیمار، نتایج آزمایش و ...)
# در یک فایل ZIP بسته‌بندی می‌شوند. این روش برخلاف بکاپ‌گیری مستقیم از SQL Server
# (دستور BACKUP DATABASE) به هیچ دسترسی خاصی در سطح فایل‌سیستم سرور SQL نیاز
# ندارد و فقط از همان اتصال دیتابیسی استفاده می‌کند که خود برنامه با آن کار
# می‌کند؛ بنابراین همیشه قابل اجراست. همین فایل ZIP برای بازیابی هم استفاده
# می‌شود.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/backup", tags=["backup"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKUP_DIR = os.getenv("BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
UPLOADS_DIR = os.path.join(BASE_DIR, "static", "uploads")

FILENAME_RE = re.compile(r"^clinic_backup_\d{8}_\d{6}\.zip$")

os.makedirs(BACKUP_DIR, exist_ok=True)

# ترتیب جدول‌ها بر اساس وابستگیِ کلید خارجی (والد قبل از فرزند) — برای درج هنگام بازیابی
INSERT_ORDER = [
    models.User,
    models.ServiceItem,
    models.Medication,
    models.Patient,
    models.Appointment,
    models.Vitals,
    models.LabTest,
    models.Invoice,
    models.InvoiceItem,
    models.Payment,
    models.VitalMedication,
]


# ---------------------------------------------------------------------------
# کمک‌کننده‌ها: تبدیل مقادیر دیتابیس <-> JSON
# ---------------------------------------------------------------------------

def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    return value


def _deserialize_value(value, column):
    if value is None:
        return None
    type_name = column.type.__class__.__name__
    if type_name == "Enum":
        enum_class = getattr(column.type, "enum_class", None)
        return enum_class(value) if enum_class else value
    if type_name == "DateTime":
        return datetime.datetime.fromisoformat(value)
    if type_name == "Date":
        return datetime.date.fromisoformat(value)
    if type_name == "Time":
        return datetime.time.fromisoformat(value)
    if type_name == "Numeric":
        return decimal.Decimal(str(value))
    return value


def _safe_filename(filename: str) -> Optional[str]:
    """جلوگیری از Path Traversal: فقط اسم فایل‌های خودِ سیستم بکاپ مجاز است."""
    name = os.path.basename(filename)
    if not FILENAME_RE.match(name):
        return None
    return name


# ---------------------------------------------------------------------------
# ساخت بکاپ
# ---------------------------------------------------------------------------

def create_backup_file() -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"clinic_backup_{ts}.zip"
    filepath = os.path.join(BACKUP_DIR, filename)
    tmp_filepath = filepath + ".tmp"

    db = SessionLocal()
    try:
        with zipfile.ZipFile(tmp_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                "app": "درمانیو",
                "created_at": datetime.datetime.now().isoformat(),
                "tables": {},
            }
            for model_cls in INSERT_ORDER:
                columns = model_cls.__table__.columns
                rows = db.query(model_cls).all()
                data = [
                    {c.name: _serialize_value(getattr(row, c.name)) for c in columns}
                    for row in rows
                ]
                manifest["tables"][model_cls.__tablename__] = len(data)
                zf.writestr(f"data/{model_cls.__tablename__}.json",
                             json.dumps(data, ensure_ascii=False, indent=2))

            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

            if os.path.isdir(UPLOADS_DIR):
                for root, _dirs, files in os.walk(UPLOADS_DIR):
                    for fname in files:
                        full_path = os.path.join(root, fname)
                        arcname = os.path.join("uploads", os.path.relpath(full_path, UPLOADS_DIR))
                        zf.write(full_path, arcname=arcname)
    except Exception:
        if os.path.exists(tmp_filepath):
            os.remove(tmp_filepath)
        raise
    finally:
        db.close()

    os.replace(tmp_filepath, filepath)
    return filename


# ---------------------------------------------------------------------------
# بازیابی از یک فایل بکاپ
# ---------------------------------------------------------------------------

def restore_from_zip(filepath: str):
    db = SessionLocal()
    is_mssql = engine.dialect.name == "mssql"
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise ValueError("این فایل یک نسخه پشتیبان معتبر نیست.")

            # ۱) حذف داده‌های فعلی (از فرزند به والد، برای رعایت کلید خارجی)
            for model_cls in reversed(INSERT_ORDER):
                db.query(model_cls).delete(synchronize_session=False)
            db.flush()

            # ۲) درج داده‌های بکاپ (از والد به فرزند)
            for model_cls in INSERT_ORDER:
                table_name = model_cls.__tablename__
                data_path = f"data/{table_name}.json"
                if data_path not in names:
                    continue
                rows = json.loads(zf.read(data_path).decode("utf-8"))
                if not rows:
                    continue
                columns = {c.name: c for c in model_cls.__table__.columns}

                if is_mssql:
                    db.execute(text(f"SET IDENTITY_INSERT {table_name} ON"))
                try:
                    for row in rows:
                        kwargs = {
                            col_name: _deserialize_value(value, columns[col_name])
                            for col_name, value in row.items()
                            if col_name in columns
                        }
                        db.add(model_cls(**kwargs))
                    db.flush()
                finally:
                    if is_mssql:
                        db.execute(text(f"SET IDENTITY_INSERT {table_name} OFF"))

            db.commit()

            # ۳) بازگردانی فایل‌های آپلودشده
            os.makedirs(UPLOADS_DIR, exist_ok=True)
            for existing in os.listdir(UPLOADS_DIR):
                existing_path = os.path.join(UPLOADS_DIR, existing)
                if os.path.isfile(existing_path) and existing != ".gitkeep":
                    os.remove(existing_path)

            for name in names:
                if name.startswith("uploads/") and not name.endswith("/"):
                    rel = os.path.relpath(name, "uploads")
                    target_path = os.path.join(UPLOADS_DIR, rel)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zf.open(name) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _list_backups():
    backups = []
    if os.path.isdir(BACKUP_DIR):
        for fname in os.listdir(BACKUP_DIR):
            if not FILENAME_RE.match(fname):
                continue
            full_path = os.path.join(BACKUP_DIR, fname)
            stat = os.stat(full_path)
            backups.append({
                "filename": fname,
                "size": stat.st_size,
                "created_at": datetime.datetime.fromtimestamp(stat.st_mtime),
            })
    backups.sort(key=lambda b: b["created_at"], reverse=True)
    return backups


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("بایت", "کیلوبایت", "مگابایت", "گیگابایت"):
        if size < 1024 or unit == "گیگابایت":
            return f"{size:,.1f} {unit}" if unit != "بایت" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:,.1f} گیگابایت"


# ---------------------------------------------------------------------------
# مسیرها (Routes) — فقط برای مدیر سیستم
# ---------------------------------------------------------------------------

@router.get("")
def backup_page(
    request: Request,
    message: Optional[str] = None,
    error: Optional[str] = None,
    user=Depends(require_roles(models.UserRole.admin)),
):
    backups = _list_backups()
    for b in backups:
        b["size_display"] = _format_size(b["size"])
    return templates.TemplateResponse(
        "backup.html",
        {"request": request, "user": user, "backups": backups, "message": message, "error": error},
    )


@router.post("/create")
def create_backup(user=Depends(require_roles(models.UserRole.admin))):
    try:
        create_backup_file()
        return RedirectResponse("/backup?message=created", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/backup?error={_short(str(exc))}", status_code=303)


@router.get("/download/{filename}")
def download_backup(filename: str, user=Depends(require_roles(models.UserRole.admin))):
    safe_name = _safe_filename(filename)
    if not safe_name:
        return RedirectResponse("/backup?error=invalid", status_code=303)
    filepath = os.path.join(BACKUP_DIR, safe_name)
    if not os.path.isfile(filepath):
        return RedirectResponse("/backup?error=notfound", status_code=303)
    return FileResponse(filepath, media_type="application/zip", filename=safe_name)


@router.post("/delete/{filename}")
def delete_backup(filename: str, user=Depends(require_roles(models.UserRole.admin))):
    safe_name = _safe_filename(filename)
    if safe_name:
        filepath = os.path.join(BACKUP_DIR, safe_name)
        if os.path.isfile(filepath):
            os.remove(filepath)
    return RedirectResponse("/backup?message=deleted", status_code=303)


@router.post("/restore/{filename}")
def restore_backup(filename: str, user=Depends(require_roles(models.UserRole.admin))):
    safe_name = _safe_filename(filename)
    if not safe_name:
        return RedirectResponse("/backup?error=invalid", status_code=303)
    filepath = os.path.join(BACKUP_DIR, safe_name)
    if not os.path.isfile(filepath):
        return RedirectResponse("/backup?error=notfound", status_code=303)
    try:
        restore_from_zip(filepath)
        return RedirectResponse("/backup?message=restored", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/backup?error={_short(str(exc))}", status_code=303)


@router.post("/restore-upload")
def restore_backup_upload(
    backup_file: UploadFile = File(...),
    user=Depends(require_roles(models.UserRole.admin)),
):
    if not backup_file.filename.lower().endswith(".zip"):
        return RedirectResponse("/backup?error=invalid", status_code=303)

    tmp_path = os.path.join(BACKUP_DIR, "_uploaded_restore.tmp.zip")
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(backup_file.file, f)
        restore_from_zip(tmp_path)
        return RedirectResponse("/backup?message=restored", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/backup?error={_short(str(exc))}", status_code=303)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _short(text_value: str, limit: int = 120) -> str:
    from urllib.parse import quote
    return quote((text_value or "خطای نامشخص")[:limit])
