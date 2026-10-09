"""Compatibility migration for the electronic-prescription tables.
Safe to run repeatedly on SQL Server. It creates missing tables via metadata,
then adds missing nullable columns that may be absent in older installations.
"""
from sqlalchemy import inspect, text
from app.database import engine, Base
from app import models  # noqa: F401


def _add_column_if_missing(conn, table, column, sql_type):
    # Use SQL Server metadata directly. This is more reliable than SQLAlchemy
    # reflection on older SQL Server/ODBC combinations.
    exists = conn.execute(text(
        "SELECT 1 WHERE COL_LENGTH(:tbl, :col) IS NOT NULL"
    ), {"tbl": "dbo." + table, "col": column}).first()
    if exists:
        return False
    conn.execute(text(f"ALTER TABLE dbo.[{table}] ADD [{column}] {sql_type} NULL"))
    print(f"Prescription schema: added {table}.{column}")
    return True


def ensure_prescription_schema():
    # First create any completely missing prescription-related tables.
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        # SQL Server installations created by older clinic versions may have
        # the prescriptions table with only the original columns. Add the
        # newer electronic-prescription columns before any ORM query runs.
        # Existing installations may have older versions of these tables.
        prescription_cols = {
            "patient_id": "INT",
            "doctor_id": "INT",
            "provider_id": "INT",
            "appointment_id": "INT",
            "prescription_date": "DATETIME2",
            "status": "VARCHAR(20)",
            "external_prescription_id": "VARCHAR(200)",
            "tracking_code": "VARCHAR(200)",
            "notes": "NVARCHAR(MAX)",
            "created_at": "DATETIME2",
            "updated_at": "DATETIME2",
        }
        for col, typ in prescription_cols.items():
            _add_column_if_missing(conn, "prescriptions", col, typ)

        item_cols = {
            "prescription_id": "INT",
            "drug_id": "INT",
            "medication_id": "INT",
            "drug_name": "NVARCHAR(250)",
            "national_drug_code": "VARCHAR(100)",
            "dosage": "NVARCHAR(150)",
            "frequency": "NVARCHAR(150)",
            "duration": "NVARCHAR(100)",
            "route": "NVARCHAR(100)",
            "instructions": "NVARCHAR(MAX)",
            "quantity": "INT",
        }
        for col, typ in item_cols.items():
            _add_column_if_missing(conn, "prescription_items", col, typ)

        provider_cols = {"code": "VARCHAR(50)", "name": "NVARCHAR(200)", "is_active": "BIT", "created_at": "DATETIME2"}
        for col, typ in provider_cols.items():
            _add_column_if_missing(conn, "insurance_providers", col, typ)

        drug_cols = {
            "national_drug_code": "VARCHAR(100)",
            "generic_name": "NVARCHAR(250)",
            "brand_name": "NVARCHAR(250)",
            "dosage_form": "NVARCHAR(100)",
            "strength": "NVARCHAR(100)",
            "unit": "NVARCHAR(50)",
            "manufacturer": "NVARCHAR(200)",
            "is_active": "BIT",
            "created_at": "DATETIME2",
        }
        for col, typ in drug_cols.items():
            _add_column_if_missing(conn, "drugs", col, typ)


def _relax_legacy_not_null(conn, table, model_cls):
    """ستون‌های قدیمی که در مدل فعلی نیستند ولی NOT NULL و بدون مقدار پیش‌فرض‌اند
    باعث خطای INSERT می‌شوند؛ آن‌ها را NULL‌پذیر می‌کنیم."""
    known = {c.name.lower() for c in model_cls.__table__.columns}
    rows = conn.execute(text(
        "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=:t AND IS_NULLABLE='NO' AND COLUMN_DEFAULT IS NULL"
    ), {"t": table}).fetchall()
    for name, dtype, length, prec, scale in rows:
        if name.lower() in known or name.lower() == "id":
            continue
        # ستون identity/computed را دست نزن
        special = conn.execute(text(
            "SELECT COLUMNPROPERTY(OBJECT_ID(:o), :c, 'IsIdentity') + COLUMNPROPERTY(OBJECT_ID(:o), :c, 'IsComputed')"
        ), {"o": f"dbo.{table}", "c": name}).scalar()
        if special:
            continue
        if dtype in ("varchar", "nvarchar", "char", "nchar", "varbinary"):
            typ = f"{dtype}({'MAX' if length in (None, -1) else length})"
        elif dtype in ("decimal", "numeric"):
            typ = f"{dtype}({prec},{scale})"
        else:
            typ = dtype
        try:
            conn.execute(text(f"ALTER TABLE dbo.[{table}] ALTER COLUMN [{name}] {typ} NULL"))
            print(f"Prescription schema: relaxed NOT NULL on {table}.{name}")
        except Exception as exc:  # noqa: BLE001
            print(f"Prescription schema: could not relax {table}.{name}: {exc}")


def relax_legacy_columns():
    with engine.begin() as conn:
        _relax_legacy_not_null(conn, "prescriptions", models.Prescription)
        _relax_legacy_not_null(conn, "prescription_items", models.PrescriptionItem)


_orig_ensure = ensure_prescription_schema


def ensure_prescription_schema():  # noqa: F811
    if engine.dialect.name != "mssql":
        return  # این مهاجرت فقط مخصوص SQL Server است؛ در SQLite جدول‌ها با create_all ساخته می‌شوند
    _orig_ensure()
    relax_legacy_columns()
