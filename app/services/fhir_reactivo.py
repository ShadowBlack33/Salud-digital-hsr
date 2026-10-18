"""
Interoperabilidad reactiva con FHIR (R21).

Cómo se entera el sistema de un dato nuevo:

  1. Al arrancar, la API registra en HAPI una Subscription con canal
     `rest-hook` (asegurar_suscripcion). Es idempotente: tiene id fijo y solo
     se reescribe si cambió algo o HAPI la marcó con error.
  2. Cuando llega una Observation al servidor FHIR (de un laboratorio, un
     dispositivo, otro sistema, o Postman), HAPI llama a
     POST {HOOK_URL_BASE}/fhir-hook/observation con la Observation en el cuerpo
     y el secreto compartido en la cabecera X-Hook-Secret.
  3. procesar_observacion() identifica al paciente por `subject.reference`,
     busca a sus clínicos responsables, les notifica (bandeja + canal en vivo)
     y deja un evento auditado con origen FHIR.

No hay sondeo: HAPI empuja. Dos protecciones evitan reacciones de más:
  · duplicados: HAPI reintenta si no recibe 2xx; la llave única
    (recurso, id, versión) en `eventos_fhir` hace que la misma Observation
    reaccione una sola vez;
  · eco: las Observations que escribe la propia API (identificador del sistema
    del hospital) no disparan nada.
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from app.core.config import get_settings
from app.core.crypto import blind_index
from app.services import bandeja
from app.services import fhir as fhir_svc
from app.services.auditoria import registrar

log = logging.getLogger("hsr.fhir_reactivo")
settings = get_settings()

ID_SUSCRIPCION = "pulso-observaciones"
RUTA_HOOK = "/fhir-hook/observation"

# Criterios de la Subscription, del más amplio al más estricto. HAPI valida el
# criterio al registrarla; se usa el primero que acepte.
CRITERIOS = (
    "Observation?",
    "Observation?_lastUpdated=gt2000-01-01",
    "Observation?status=registered,preliminary,final,amended,corrected",
)

# Nombres de los códigos LOINC más comunes, para que el aviso diga algo útil.
LOINC_NOMBRES = {
    "2339-0": "glucosa", "2345-7": "glucosa", "15074-8": "glucosa", "1558-6": "glucosa en ayunas",
    "8867-4": "frecuencia cardiaca", "9279-1": "frecuencia respiratoria",
    "59408-5": "saturación de oxígeno", "2708-6": "saturación de oxígeno", "8310-5": "temperatura",
    "8480-6": "presión sistólica", "8462-4": "presión diastólica", "85354-9": "presión arterial",
    "2823-3": "potasio", "2524-7": "lactato", "718-7": "hemoglobina",
}


# ------------------------------------------------------------ Subscription
def recurso_suscripcion(criterio: str) -> dict:
    return {
        "resourceType": "Subscription",
        "id": ID_SUSCRIPCION,
        "status": "requested",   # HAPI la pasa a "active" al validarla
        "reason": "Pulso reacciona a cada Observation nueva (notifica al médico responsable)",
        "criteria": criterio,
        "channel": {
            "type": "rest-hook",
            "endpoint": f"{settings.hook_url_base.rstrip('/')}{RUTA_HOOK}",
            "payload": "application/fhir+json",
            "header": [f"X-Hook-Secret: {settings.hook_secret}"],
        },
    }


def asegurar_suscripcion(cliente: httpx.Client | None = None) -> str:
    """
    Deja registrada y activa la Subscription en HAPI. Devuelve "ya_activa",
    "registrada" o lanza si HAPI no responde. Con HOOK_SECRET vacío no se
    registra nada: el receptor rechazaría todas las llamadas.
    """
    if not settings.hook_secret:
        raise RuntimeError("HOOK_SECRET vacío: no se puede registrar la Subscription")
    base = settings.fhir_base_url.rstrip("/")
    propio = cliente is None
    c = cliente or httpx.Client(timeout=settings.fhir_timeout)
    try:
        r = c.get(f"{base}/Subscription/{ID_SUSCRIPCION}")
        if r.status_code == 200:
            actual = r.json()
            canal = actual.get("channel", {})
            deseada = recurso_suscripcion(actual.get("criteria", CRITERIOS[0]))["channel"]
            if (actual.get("status") in ("active", "requested")
                    and canal.get("endpoint") == deseada["endpoint"]
                    and canal.get("header") == deseada["header"]):
                return "ya_activa"
        ultimo = None
        for criterio in CRITERIOS:
            ultimo = c.put(f"{base}/Subscription/{ID_SUSCRIPCION}", json=recurso_suscripcion(criterio),
                           headers={"Content-Type": "application/fhir+json"})
            if ultimo.status_code in (200, 201):
                log.info("Subscription FHIR registrada con el criterio %r", criterio)
                return "registrada"
            log.warning("HAPI rechazó el criterio %r (%s)", criterio, ultimo.status_code)
        raise RuntimeError(f"HAPI no aceptó la Subscription: {ultimo.status_code} {ultimo.text[:200]}")
    finally:
        if propio:
            c.close()


async def mantener_suscripcion() -> None:
    """
    Tarea de fondo: HAPI puede arrancar después que la API, así que se reintenta
    hasta lograrlo y luego se verifica de vez en cuando (por si alguien la borró
    o quedó en error).
    """
    espera = 10
    while True:
        try:
            estado = await run_in_threadpool(asegurar_suscripcion)
            if estado == "registrada":
                log.info("Subscription FHIR lista")
            espera = 300
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Subscription FHIR pendiente: %s", e)
            espera = min(espera * 2, 120) if espera < 300 else 10
        await asyncio.sleep(espera)


# -------------------------------------------------------------- Observation
def _paciente_de(db, obs: dict) -> str | None:
    """documento_bidx del paciente al que se refiere la Observation, o None."""
    sujeto = obs.get("subject") or {}
    ref = sujeto.get("reference") or ""
    m = re.search(r"Patient/([A-Za-z0-9\-.]{1,64})", ref)
    if m:
        fila = db.execute(text("SELECT documento_bidx FROM pacientes WHERE fhir_patient_id = :f AND activo"),
                          {"f": m.group(1)}).first()
        if fila:
            return fila[0]
    ident = sujeto.get("identifier") or {}
    valor = ident.get("value")
    if valor:
        # El identificador del hospital es el propio índice ciego; el de la cédula, su valor.
        for candidato in (str(valor).strip(), blind_index(str(valor), "documento")):
            fila = db.execute(text("SELECT documento_bidx FROM pacientes WHERE documento_bidx = :b AND activo"),
                              {"b": candidato}).first()
            if fila:
                return fila[0]
    return None


def _clinicos_responsables(db, paciente_id: str) -> list[int]:
    """
    Médicos y especialistas a cargo del paciente: quien lo registró, el médico
    responsable o anestesiólogo de un encuentro activo, y el especialista de una
    remisión pendiente o aceptada. (Las mismas reglas del alcance `assigned`.)
    """
    filas = db.execute(text("""
        SELECT DISTINCT u.id FROM usuarios u JOIN roles r ON r.id = u.rol_id
        WHERE u.activo AND r.codigo IN ('medico', 'especialista') AND (
              u.id = (SELECT created_by FROM pacientes WHERE documento_bidx = :p)
           OR u.personal_id IN (SELECT medico_responsable_id FROM encuentros WHERE paciente_id = :p AND activo)
           OR u.personal_id IN (SELECT anestesiologo_id FROM encuentros WHERE paciente_id = :p AND activo)
           OR u.personal_id IN (SELECT especialista_id FROM remisiones
                                WHERE paciente_id = :p AND estado IN ('pendiente', 'aceptada'))
        )
    """), {"p": paciente_id}).all()
    return [f[0] for f in filas]


def _resumen(obs: dict) -> tuple[str, str | None]:
    """(descripción del aviso, código LOINC) de la Observation."""
    codigos = (obs.get("code") or {}).get("coding") or []
    loinc = next((c for c in codigos if c.get("system") == fhir_svc.SYS_LOINC), None)
    cod = (loinc or (codigos[0] if codigos else {})).get("code")
    nombre = LOINC_NOMBRES.get(cod or "") or (loinc or (codigos[0] if codigos else {})).get("display") \
        or (obs.get("code") or {}).get("text") or "observación"
    valor = obs.get("valueQuantity")
    if valor and valor.get("value") is not None:
        texto = f"{valor['value']} {valor.get('unit') or valor.get('code') or ''}".strip()
    elif obs.get("valueString"):
        texto = str(obs["valueString"])[:60]
    else:
        texto = None
    sistema = "LOINC " if loinc else ""
    partes = [f"Llegó una {nombre} desde FHIR"]
    if cod:
        partes[0] += f" ({sistema}{cod})"
    return (partes[0] + (f": {texto}." if texto else "."), cod)


def procesar_observacion(db, obs: dict) -> dict:
    """
    Reacciona a una Observation nueva. Devuelve {"resultado": ...}; el llamador
    hace el commit (la notificación, la auditoría y el registro de evento se
    confirman juntos, y el evento en vivo sale después del commit).
    """
    oid = str(obs.get("id") or "")
    version = str((obs.get("meta") or {}).get("versionId") or "")
    if not oid:
        return {"resultado": "ignorada", "motivo": "sin id"}

    # El eco de lo que la propia API escribió en HAPI no reacciona.
    if any((i.get("system") or "").startswith(fhir_svc.SYS_HOSPITAL) for i in obs.get("identifier") or []):
        return {"resultado": "origen_api"}

    nuevo = db.execute(text("""
        INSERT INTO eventos_fhir (recurso_tipo, recurso_id, version) VALUES ('Observation', :i, :v)
        ON CONFLICT ON CONSTRAINT uq_evento_fhir DO NOTHING RETURNING id
    """), {"i": oid, "v": version}).first()
    if nuevo is None:
        return {"resultado": "duplicada"}   # HAPI reintentó: ya se atendió

    paciente_id = _paciente_de(db, obs)
    mensaje, codigo = _resumen(obs)
    base = {"origen": "fhir", "observation_id": oid, "codigo": codigo}
    if paciente_id is None:
        db.execute(text("UPDATE eventos_fhir SET resultado = 'sin_paciente' WHERE id = :i"), {"i": nuevo[0]})
        registrar(db, None, "observacion_fhir", oid, "evento_fhir", resultado="error",
                  valor_nuevo={**base, "motivo": "no se identificó al paciente"})
        return {"resultado": "sin_paciente"}

    db.execute(text("UPDATE eventos_fhir SET paciente_id = :p WHERE id = :i"), {"p": paciente_id, "i": nuevo[0]})
    destinatarios = _clinicos_responsables(db, paciente_id)
    bandeja.notificar(db, destinatarios, "fhir_observation", mensaje, paciente_id=paciente_id,
                      datos={"observation_id": oid, "codigo": codigo, "origen": "fhir"})
    registrar(db, None, "paciente", paciente_id, "evento_fhir",
              valor_nuevo={**base, "paciente_id": paciente_id, "notificados": len(destinatarios)})
    return {"resultado": "procesada", "notificados": len(destinatarios)}
