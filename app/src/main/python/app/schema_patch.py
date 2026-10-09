"""افزودن ستون‌های جدید به جدول‌های موجود (جدول‌های تازه را create_all می‌سازد).
این فایل هر بار بدون خطا قابل اجراست."""
from sqlalchemy import text

STATEMENTS = [
    "IF COL_LENGTH('insurance_companies','provider_code') IS NULL "
    "ALTER TABLE insurance_companies ADD provider_code VARCHAR(30) NULL",
    "IF COL_LENGTH('medications','national_code') IS NULL "
    "ALTER TABLE medications ADD national_code VARCHAR(50) NULL",
]


def apply(engine):
    with engine.begin() as conn:
        for sql in STATEMENTS:
            conn.execute(text(sql))
