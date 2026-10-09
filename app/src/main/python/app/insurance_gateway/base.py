from abc import ABC, abstractmethod

class InsuranceAdapter(ABC):
    """قرارداد ارتباط با بیمه. Endpoint واقعی هر سازمان بعداً در Adapter رسمی آن پیاده‌سازی می‌شود."""
    def __init__(self, provider, config=None):
        self.provider = provider
        self.config = config

    @abstractmethod
    def submit_prescription(self, prescription):
        raise NotImplementedError

    def get_status(self, prescription):
        return {"ok": False, "status": "not_configured", "message": "سرویس رسمی هنوز پیکربندی نشده است."}

    def cancel_prescription(self, prescription):
        return {"ok": False, "status": "not_configured", "message": "سرویس رسمی هنوز پیکربندی نشده است."}
