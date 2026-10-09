from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import Base, engine, SessionLocal
from app import seed
from app import booking_settings as booking_settings_mod
from app.prescription_schema import ensure_prescription_schema
from app.routers import (
    auth, dashboard, patients, appointments, lab_tests, finance, finance_items,
    users, medications, vitals, doctor, backup, insurance, prescriptions, booking, settings,
)

Base.metadata.create_all(bind=engine)
# Compatibility migration for older SQL Server databases.
try:
    ensure_prescription_schema()
except Exception as exc:
    print("Prescription schema check warning:", exc)

app = FastAPI(title="درمانیو — سامانه مدیریت کلینیک")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(patients.router)
app.include_router(appointments.router)
app.include_router(lab_tests.router)
app.include_router(finance.router)
app.include_router(finance_items.router)
app.include_router(users.router)
app.include_router(medications.router)
app.include_router(vitals.router)
app.include_router(doctor.router)
app.include_router(backup.router)
app.include_router(insurance.router)
app.include_router(prescriptions.router)
app.include_router(booking.router)
app.include_router(settings.router)


@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        seed.seed_admin(db)
        seed.seed_insurance_companies(db)
        seed.seed_service_items(db)
        seed.seed_medications(db)
        seed.seed_insurance_providers(db)
        seed.seed_drugs(db)
        booking_settings_mod.ensure_settings(db)
    finally:
        db.close()


# فایل‌های PWA باید از ریشه سایت سرو بشن تا نصب روی موبایل/PC درست کار کنه
@app.get("/manifest.json")
def manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    return FileResponse("static/service-worker.js", media_type="application/javascript")


# اگر کاربر لاگین نبود، به جای خطای خام، به صفحه ورود هدایتش کن
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request, exc):
    if exc.status_code == 303 and exc.headers and "location" in {k.lower() for k in exc.headers.keys()}:
        from fastapi.responses import RedirectResponse
        location = exc.headers.get("Location") or exc.headers.get("location")
        return RedirectResponse(location, status_code=303)
    return await http_exception_handler(request, exc)
