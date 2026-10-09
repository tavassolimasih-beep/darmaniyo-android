from typing import Optional

from .base import InsuranceGateway
from .providers import TaminGateway, SalamatGateway, ArmedForcesGateway

_GATEWAYS = {g.code: g for g in (TaminGateway(), SalamatGateway(), ArmedForcesGateway())}


def get_gateway(provider_code: Optional[str]) -> Optional[InsuranceGateway]:
    return _GATEWAYS.get(provider_code or "")
