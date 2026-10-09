"""سه بیمهٔ پشتیبانی‌شده. تا وقتی وب‌سرویس رسمی تنظیم نشده، نتیجه «MANUAL» است
(پزشک نسخه را با دکمهٔ کپی در سامانهٔ بیمه ثبت می‌کند).

تنظیمات اختیاری در .env (برای هر بیمه با پیشوند TAMIN / SALAMAT / ARMED):
    TAMIN_PORTAL_URL=   آدرس سامانهٔ نسخه الکترونیک (فقط برای دکمهٔ باز کردن سامانه)
    TAMIN_API_URL=      آدرس وب‌سرویس رسمی (بعد از دریافت از بیمه)
    TAMIN_API_USER=     نام کاربری مرکز/پزشک
    TAMIN_API_PASSWORD= رمز عبور

برای وصل کردن وب‌سرویس رسمی: متد _send همان کلاس را بنویسید، داده را به فرمت
مستندات بیمه تبدیل و ارسال کنید و SubmitResult(SENT, tracking_code=...) برگردانید.
"""
import os

from .base import InsuranceGateway, PrescriptionData, SubmitResult, MANUAL, SENT, FAILED


class _EnvGateway(InsuranceGateway):
    env_prefix = ""

    def _env(self, key: str) -> str:
        return (os.getenv("%s_%s" % (self.env_prefix, key)) or "").strip()

    def portal_url(self) -> str:
        return self._env("PORTAL_URL")

    def is_configured(self) -> bool:
        return bool(self._env("API_URL"))

    def submit(self, data: PrescriptionData) -> SubmitResult:
        if not self.is_configured():
            return SubmitResult(
                MANUAL,
                message="وب‌سرویس رسمی %s تنظیم نشده؛ نسخه را در سامانهٔ بیمه ثبت کنید." % self.title,
            )
        try:
            return self._send(data)
        except NotImplementedError:
            return SubmitResult(
                FAILED,
                message="آدرس وب‌سرویس %s تنظیم شده ولی کد اتصال هنوز نوشته نشده است." % self.title,
            )

    def _send(self, data: PrescriptionData) -> SubmitResult:
        """اینجا را بعد از دریافت مستندات رسمی پیاده کنید.

        نمونه:
            resp = requests.post(self._env("API_URL"), json={...}, timeout=20,
                                 auth=(self._env("API_USER"), self._env("API_PASSWORD")))
            resp.raise_for_status()
            return SubmitResult(SENT, tracking_code=resp.json()["trackingCode"],
                                response_payload=resp.text)
        """
        raise NotImplementedError


class TaminGateway(_EnvGateway):
    code = "tamin"
    title = "تأمین اجتماعی"
    env_prefix = "TAMIN"


class SalamatGateway(_EnvGateway):
    code = "salamat"
    title = "بیمه سلامت"
    env_prefix = "SALAMAT"


class ArmedForcesGateway(_EnvGateway):
    code = "armed_forces"
    title = "نیروهای مسلح"
    env_prefix = "ARMED"
