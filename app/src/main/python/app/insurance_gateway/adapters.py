from .base import InsuranceAdapter

class UnconfiguredAdapter(InsuranceAdapter):
    def submit_prescription(self, prescription):
        return {
            "ok": False,
            "status": "not_configured",
            "message": "API رسمی این بیمه هنوز در درمانیو پیکربندی نشده است؛ نسخه در وضعیت Pending باقی می‌ماند."
        }

class TaminSocialSecurityAdapter(UnconfiguredAdapter):
    pass

class IranHealthInsuranceAdapter(UnconfiguredAdapter):
    pass

class ArmedForcesAdapter(UnconfiguredAdapter):
    pass

class ManualAdapter(UnconfiguredAdapter):
    pass

ADAPTERS = {
    "TAMIN": TaminSocialSecurityAdapter,
    "IHIO": IranHealthInsuranceAdapter,
    "ARMED_FORCES": ArmedForcesAdapter,
}

def get_adapter(provider, config=None):
    cls = ADAPTERS.get(provider.code, ManualAdapter)
    return cls(provider, config)
