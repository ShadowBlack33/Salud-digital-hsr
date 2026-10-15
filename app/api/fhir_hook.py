"""
Receptor del rest-hook de la Subscription FHIR (R21).

HAPI llama aquí, por la red interna de Docker (http://api:8000/fhir-hook/...),
cuando llega una Observation. nginx NO expone esta ruta hacia afuera
(/api/fhir-hook/ responde 404); aun así se exige el secreto compartido en la
cabecera X-Hook-Secret, comparado en tiempo constante. Sin HOOK_SECRET
configurado, el receptor rechaza todo (falla cerrado).

Acepta POST y PUT y cualquier sub-ruta: según la versión, HAPI entrega la
Observation con PUT {endpoint}/Observation/{id} o con POST al endpoint. Siempre
responde 200 si pudo leerla, para que HAPI no reintente indefinidamente.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.deps import SessionLocal
from app.services import fhir_reactivo

log = logging.getLogger("hsr.fhir_hook")
settings = get_settings()
router = APIRouter(prefix="/fhir-hook", include_in_schema=False)


def _procesar(obs: dict) -> dict:
    with SessionLocal() as db:
        try:
            resultado = fhir_reactivo.procesar_observacion(db, obs)
            db.commit()
            return resultado
        except Exception:
            db.rollback()
            raise


@router.api_route("/{ruta:path}", methods=["POST", "PUT"])
async def recibir(ruta: str, request: Request):
    enviado = request.headers.get("x-hook-secret", "")
    if not settings.hook_secret or not hmac.compare_digest(enviado.encode(), settings.hook_secret.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Secreto del hook inválido")
    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001 -- ping de HAPI sin cuerpo
        return {"resultado": "ignorada", "motivo": "sin cuerpo"}
    if not isinstance(cuerpo, dict) or cuerpo.get("resourceType") != "Observation":
        return {"resultado": "ignorada", "motivo": "no es una Observation"}
    return await run_in_threadpool(_procesar, cuerpo)
