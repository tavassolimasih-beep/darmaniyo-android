import datetime
from app import models
from .adapters import get_adapter

def submit_prescription(db, prescription):
    provider = prescription.provider
    if not provider:
        prescription.status = models.PrescriptionStatus.pending
        db.commit()
        return None
    config = (db.query(models.InsuranceProviderConfig)
              .filter(models.InsuranceProviderConfig.provider_id == provider.id)
              .order_by(models.InsuranceProviderConfig.id.desc()).first())
    adapter = get_adapter(provider, config)
    result = adapter.submit_prescription(prescription)
    now = datetime.datetime.utcnow()
    transmission = models.PrescriptionTransmission(
        prescription_id=prescription.id, provider_id=provider.id,
        status=(models.TransmissionStatus.submitted if result.get("ok") else models.TransmissionStatus.pending),
        response_code=str(result.get("status") or ""),
        response_message=result.get("message"), last_attempt_at=now,
        retry_count=1,
    )
    db.add(transmission)
    prescription.status = models.PrescriptionStatus.submitted if result.get("ok") else models.PrescriptionStatus.pending
    db.commit()
    return transmission
