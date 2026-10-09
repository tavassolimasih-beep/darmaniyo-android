"""رابط مشترک اتصال به سامانهٔ نسخه الکترونیک بیمه‌ها.

هر بیمه یک Gateway دارد که متد submit(data) را پیاده می‌کند. بقیهٔ برنامه
(ثبت نسخه، نمایش وضعیت، ارسال مجدد) فقط با همین رابط کار می‌کند؛ پس وقتی
وب‌سرویس رسمی را گرفتید فقط باید متد _send همان بیمه را بنویسید.
"""
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# وضعیت‌های ثبت نسخه در سامانهٔ بیمه
MANUAL = "manual"   # وب‌سرویس نیست؛ پزشک باید دستی در سامانهٔ بیمه ثبت کند
SENT = "sent"       # با موفقیت ثبت شد (کد پیگیری دارد)
FAILED = "failed"   # خطا؛ قابل ارسال مجدد

STATUS_LABELS = {MANUAL: "در انتظار ثبت دستی در سامانهٔ بیمه", SENT: "ثبت‌شده در سامانهٔ بیمه", FAILED: "خطا در ثبت"}

# کد داخلی بیمه -> نام فارسی
PROVIDERS = {
    "tamin": "تأمین اجتماعی",
    "salamat": "بیمه سلامت",
    "armed_forces": "نیروهای مسلح",
}


@dataclass
class PrescriptionItemData:
    name: str
    national_code: str = ""
    dose: str = ""
    frequency: str = ""
    duration_days: Optional[int] = None
    quantity: Optional[int] = None
    instructions: str = ""


@dataclass
class PrescriptionData:
    prescription_id: int
    patient_name: str
    patient_national_code: str
    insurance_name: str
    provider_code: str
    doctor_name: str
    visit_date: str
    diagnosis: str = ""
    notes: str = ""
    items: List[PrescriptionItemData] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_clipboard_text(self):
        """متن آمادهٔ کپی برای ثبت دستی در سامانهٔ بیمه."""
        lines = [
            "بیمار: %s" % self.patient_name,
            "کد ملی: %s" % (self.patient_national_code or "-"),
            "بیمه: %s" % self.insurance_name,
            "پزشک: %s" % self.doctor_name,
            "تاریخ ویزیت: %s" % self.visit_date,
        ]
        if self.diagnosis:
            lines.append("تشخیص: %s" % self.diagnosis)
        lines.append("")
        for i, it in enumerate(self.items, 1):
            parts = [it.name]
            if it.national_code:
                parts.append("کد: %s" % it.national_code)
            if it.dose:
                parts.append("دوز: %s" % it.dose)
            if it.frequency:
                parts.append("تکرار: %s" % it.frequency)
            if it.duration_days:
                parts.append("مدت: %s روز" % it.duration_days)
            if it.quantity:
                parts.append("تعداد: %s" % it.quantity)
            if it.instructions:
                parts.append("دستور: %s" % it.instructions)
            lines.append("%d) %s" % (i, " | ".join(parts)))
        if self.notes:
            lines += ["", "توضیحات: %s" % self.notes]
        return "\n".join(lines)


@dataclass
class SubmitResult:
    status: str
    tracking_code: Optional[str] = None
    message: str = ""
    response_payload: Optional[str] = None


class InsuranceGateway:
    """کلاس پایهٔ اتصال به یک بیمه."""

    code = ""
    title = ""

    def portal_url(self) -> str:
        """آدرس سامانهٔ نسخه الکترونیک (از .env) برای دکمهٔ «باز کردن سامانه»؛ اختیاری."""
        return ""

    def is_configured(self) -> bool:
        """آیا وب‌سرویس رسمی تنظیم شده است؟"""
        return False

    def submit(self, data: PrescriptionData) -> SubmitResult:
        raise NotImplementedError
