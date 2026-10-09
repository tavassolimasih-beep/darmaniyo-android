"""ارسال پیامک — پشتیبانی از کاوه‌نگار و حالت شبیه‌سازی (بدون کلید واقعی)."""
from __future__ import annotations

import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger("darmaniyo.sms")

SMS_ENABLED = os.getenv("SMS_ENABLED", "false").lower() in ("1", "true", "yes")
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "kavenegar").lower()
SMS_API_KEY = os.getenv("SMS_API_KEY", "").strip()
SMS_SENDER = os.getenv("SMS_SENDER", "10008663").strip()
SMS_DRY_RUN = os.getenv("SMS_DRY_RUN", "true").lower() in ("1", "true", "yes")


def _normalize_mobile(mobile: str) -> str:
    mobile = (mobile or "").strip().replace(" ", "").replace("-", "")
    if mobile.startswith("0098"):
        mobile = "0" + mobile[4:]
    if mobile.startswith("+98"):
        mobile = "0" + mobile[3:]
    if mobile.startswith("98") and len(mobile) == 12:
        mobile = "0" + mobile[2:]
    return mobile


def send_sms(mobile: str, message: str) -> dict:
    """ارسال پیامک. در صورت نبود کلید یا DRY_RUN فقط لاگ می‌کند."""
    mobile = _normalize_mobile(mobile)
    if not mobile or len(mobile) < 10:
        return {"ok": False, "message": "شماره موبایل نامعتبر است"}

    if not SMS_ENABLED or SMS_DRY_RUN or not SMS_API_KEY:
        logger.info("[SMS-DRY] to=%s msg=%s", mobile, message)
        return {
            "ok": True,
            "dry_run": True,
            "message": "پیامک در حالت آزمایشی ثبت شد (ارسال واقعی نشده)",
        }

    try:
        if SMS_PROVIDER == "kavenegar":
            return _send_kavenegar(mobile, message)
        return {"ok": False, "message": f"ارائه‌دهنده پیامک ناشناخته: {SMS_PROVIDER}"}
    except Exception as exc:
        logger.exception("SMS send failed")
        return {"ok": False, "message": str(exc)}


def _send_kavenegar(mobile: str, message: str) -> dict:
    params = urllib.parse.urlencode(
        {
            "receptor": mobile,
            "sender": SMS_SENDER,
            "message": message,
        }
    )
    url = f"https://api.kavenegar.com/v1/{SMS_API_KEY}/sms/send.json?{params}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return {"ok": True, "dry_run": False, "provider": "kavenegar", "raw": body}


def appointment_confirm_message(
    patient_name: str,
    date_jalali: str,
    time_str: str,
    clinic_name: str = "کلینیک",
) -> str:
    return (
        f"{clinic_name}\n"
        f"نوبت {patient_name} ثبت شد.\n"
        f"تاریخ: {date_jalali}\n"
        f"ساعت: {time_str}\n"
        f"لطفاً ۱۵ دقیقه زودتر تشریف بیاورید."
    )
