"""GET /api/tenant-init — liefert Tenant-Key + Metadaten fuer Frontend-Init.

Authentifizierung: X-API-Key Header (bestehende get_tenant Dependency).
Der Endpoint validiert den Key und gibt die noetigen Frontend-Initialisierungsdaten zurueck.
"""
from fastapi import APIRouter, Depends

from dependencies import get_tenant
from models.tenant import Tenant

router = APIRouter()


@router.get("/tenant-init")
async def tenant_init(tenant: Tenant = Depends(get_tenant)):
    """Validiert den API-Key und gibt Tenant-Metadaten zurueck.

    Wird vom Frontend beim Start aufgerufen, um den gespeicherten Key
    zu verifizieren und Tenant-Daten zu laden.
    """
    return {
        "tenant_key": tenant.api_key,
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
    }
