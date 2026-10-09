from sqlalchemy.orm import Session
from app import models
from app.security import hash_password


def seed_admin(db: Session):
    existing = db.query(models.User).filter(models.User.username == "admin").first()
    if existing:
        return
    admin = models.User(
        full_name="مدیر سیستم",
        username="admin",
        password_hash=hash_password("admin123"),
        role=models.UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    #print("کاربر ادمین پیش‌فرض ساخته شد -> نام کاربری: admin | رمز عبور: admin123")


def _normalize_service_name(value: str) -> str:
    """Normalize Persian/Arabic variants so service names are compared safely."""
    if not value:
        return ""
    return (
        str(value)
        .strip()
        .replace("ي", "ی")
        .replace("ى", "ی")
        .replace("ك", "ک")
        .replace("ۀ", "ه")
        .replace("ة", "ه")
        .replace("‌", "")  # ZWNJ
        .replace("‏", "")  # RLM
        .replace("‎", "")  # LRM
        .replace("  ", " ")
    )




def seed_insurance_companies(db: Session):
    """بیمه‌های نمونه؛ درصدها قابل ویرایش از بخش بیمه‌ها هستند."""
    defaults = [
        ("بانک کشاورزی", 20),
        ("نیروهای مسلح", 30),
    ]
    # Compare using normalized names: SQL Server's collation treats Arabic/Persian
    # variants (ي/ی, ك/ک) as equal for the UNIQUE index, but a plain Python dict
    # lookup does not, which previously caused a duplicate INSERT at startup.
    existing = {_normalize_service_name(x.name) for x in db.query(models.InsuranceCompany).all()}
    for name, percent in defaults:
        key = _normalize_service_name(name)
        if key in existing:
            continue
        try:
            db.add(models.InsuranceCompany(name=name, coverage_percent=percent, is_active=True))
            db.commit()
            existing.add(key)
        except Exception:
            db.rollback()  # never block application startup over a sample row


def seed_service_items(db: Session):
    """Seed required diagnostic services without ever inserting duplicates.

    Existing databases may contain Arabic/Persian Unicode variants such as
    ``مري`` vs ``مری``.  SQL Server collations do not always compare these
    variants the same way as Python strings, so the complete existing list is
    normalized in Python before any INSERT is attempted.
    """
    required_items = [
        "تست ورزش",
        "تست عروق",
        "اکو 4 بعدی",
        "کانتراست اکو",
        "اکو معمولی",
        "اکو مادرزادی",
        "اکو تیشو",
        "هالتر فشار",
        "بادی آنالیز",
        "نوار قلب (ECG)",
        "اکو قلب",
        "اکو از راه مری (TEE)",
        "هولتر قلب",
        "آنژیوگرافی",
    ]

    # IMPORTANT: load existing rows first.  Do not use one bulk INSERT because
    # one Unicode variant can still collide with SQL Server's UNIQUE index.
    existing_rows = db.query(models.ServiceItem).all()
    existing_by_normalized = {}
    for row in existing_rows:
        key = _normalize_service_name(row.name)
        if key and key not in existing_by_normalized:
            existing_by_normalized[key] = row

    next_order = max((row.sort_order or 0 for row in existing_rows), default=-1) + 1
    changed = False

    for name in required_items:
        key = _normalize_service_name(name)
        existing = existing_by_normalized.get(key)

        if existing is not None:
            if not existing.is_active:
                existing.is_active = True
                changed = True
            continue

        row = models.ServiceItem(
            name=name,
            sort_order=next_order,
            is_active=True,
        )
        db.add(row)
        # Also track newly-added names so duplicate values inside this seed
        # list can never be inserted twice in the same transaction.
        existing_by_normalized[key] = row
        next_order += 1
        changed = True

    if changed:
        db.commit()
    else:
        # No writes were made.  Keeping the session clean is useful during startup.
        db.expire_all()


def seed_medications(db: Session):
    """لیست اولیه‌ی داروها را فقط یک‌بار (اگر جدول خالی بود) از روی فرم دارویی کلینیک
    اضافه می‌کند. بعد از این، لیست کاملاً از صفحه‌ی «لیست داروها» قابل مدیریت است.

    ⚠️ نکته‌ی مهم: این مقادیر با استخراج متن (OCR) از فرم اسکن‌شده‌ی کلینیک تهیه شده‌اند.
    برخی خانه‌های آن فرم (به‌خصوص چند ردیف نزدیک آتورواستاتین/رزواستاتین/آملودیپین) در
    اسکن به‌وضوح قابل تفکیک نبودند. پیش از استفاده‌ی بالینی، حتماً از صفحه‌ی «لیست داروها»
    یک‌به‌یک نام و دوزها را با فرم کاغذی اصلی تطبیق و در صورت نیاز اصلاح کنید.
    """
    existing = db.query(models.Medication).first()
    if existing:
        return
    # (نام دارو, دوزهای رایج به‌صورت رشته‌ی جدا شده با کاما یا None اگر دوز ثابتی ندارد)
    default_meds = [
        ("آسپرین", "80, 81"),
        ("پلاویکس (کلوپیدوگرل)", "75"),
        ("والزومیکس", "5/80, 5/160, 10/160"),
        ("والزومیکس HCT", "5/160/12.5, 10/160/12.5"),
        ("کنکور (بیزوپرولول)", "2.5, 5, 10"),
        ("آربیتوین (آملودیپین/تلمیزارتان)", "40/5, 40/10, 80/5, 80/10"),
        ("پروپرانولول", "10, 20, 40"),
        ("آربیکور پلاس", "25, 50"),
        ("متورال", "50"),
        ("تلمیزارتان (آربیکور)", "40, 80"),
        ("متوپرولول", "23.75, 47.5, 95"),
        ("والزارتان اچ", "80/12.5, 160/12.5"),
        ("دیلتیازم", "60"),
        ("والزارتان", "40, 80, 160"),
        ("وراپامیل", "40"),
        ("لوزارتان اچ", "50/12.5, 100/12.5, 100/25"),
        ("دیگوکسین", "0.25"),
        ("لوزارتان", "25, 50"),
        ("هیدروکلروتیازید", "25, 50"),
        ("آتورواستاتین", "10, 20, 40"),
        ("رزواستاتین", "5, 10, 20, 40"),
        ("آملودیپین", "2.5, 5, 10"),
        ("بمپدوئیک اسید", None),
        ("فینرنون", "10, 20"),
        ("کروزت", "10/10, 20/10, 40/10"),
        ("اپلرنون", "25, 50"),
        ("نیتروکانتین", "2.6, 6.4"),
        ("اسپیرونولاکتون", "25, 100"),
        ("فروزماید", "20, 40"),
        ("کلردیازپوکسید", "5, 10"),
        ("آرترستان", "50, 100, 200"),
        ("بوسپیرون", "5, 10"),
        ("امپاگلیفلوزین", "10, 25"),
        ("فلوکستین", "10, 20"),
        ("متفورمین", "500, 1000"),
        ("لگزاتال", "10, 20"),
        ("زیپمت", "50/500, 50/1000"),
        ("اکسابین", "2.5, 10, 15, 20"),
        ("داکسپین", "10, 25"),
        ("آسنترا (سرترالین)", "50, 100"),
        ("آپیکسابان", "2.5, 5"),
        ("وارفارین", None),
        ("رامیلتون", "8"),
        ("پنتوپرازول", "20, 40"),
        ("ملاتونین", "3, 5"),
        ("اس‌امپرازول", "20, 40"),
        ("آلپرازولام", "0.5, 1"),
        ("فاموتیدین", "20, 40"),
        ("کلونازپام", "1, 2"),
        ("لووتیروکسین", "50, 100"),
        ("گاباپنتین", "100, 300, 400"),
    ]
    for index, (name, doses) in enumerate(default_meds):
        db.add(models.Medication(name=name, dosage_options=doses, sort_order=index))
    db.commit()


def seed_insurance_providers(db: Session):
    """بیمه‌گرهای هدف نسخه الکترونیک؛ بدون Endpoint یا اعتبارنامه واقعی."""
    defaults = [
        ("TAMIN", "سازمان تأمین اجتماعی"),
        ("IHIO", "بیمه سلامت ایران"),
        ("ARMED_FORCES", "بیمه نیروهای مسلح"),
    ]
    existing = {x.code for x in db.query(models.InsuranceProvider).all()}
    changed = False
    for code, name in defaults:
        if code in existing:
            continue
        db.add(models.InsuranceProvider(code=code, name=name, is_active=True))
        existing.add(code); changed = True
    if changed:
        db.commit()


def seed_drugs(db: Session):
    """انتقال idempotent داروهای فعلی به کاتالوگ نسخه.

    کد ملی دارو در ابتدا ممکن است NULL باشد؛ در SQL Server نباید روی این
    ستون UNIQUE constraint معمولی داشته باشیم چون چند داروی بدون کد ملی
    کاملاً معتبر هستند.
    """
    meds = (db.query(models.Medication)
            .filter(models.Medication.is_active == True)
            .order_by(models.Medication.sort_order, models.Medication.name)
            .all())

    existing = {(d.generic_name.strip(), (d.strength or '').strip())
                for d in db.query(models.Drug).all()}
    changed = False

    for med in meds:
        name = (med.name or '').strip()
        if not name:
            continue
        doses = [x.strip() for x in (med.dosage_options or '').split(',') if x.strip()]
        first_dose = doses[0] if doses else None
        key = (name, first_dose or '')
        if key in existing:
            continue
        db.add(models.Drug(generic_name=name, strength=first_dose, is_active=True))
        existing.add(key)
        changed = True

    if changed:
        db.commit()
