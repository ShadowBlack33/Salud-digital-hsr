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
  3. procesar_observacion() identifica al paciente por `subject.reference`
     (Patient/{id}) o por su número de historia (MRN), GUARDA el resultado en
     `observaciones` (origen 'fhir_externo', ligado al encuentro activo si
     hay uno), avisa a sus clínicos responsables (bandeja + canal en vivo) y
     deja un evento auditado con origen FHIR.

Ya no se acepta la cédula como identificador: quien la conociera podía
mandarle resultados a cualquier paciente. Publicar en /fhir exige además el
token de la cuenta de integración (app/api/puerta_fhir.py).

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
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _paciente_de(db, obs: dict) -> str | None:
    """
    documento_bidx del paciente al que se refiere la Observation, o None.
    Solo por Patient/{id} del servidor FHIR o por el MRN del hospital (uuid);
    nunca por cédula.
    """
    sujeto = obs.get("subject") or {}
    ref = sujeto.get("reference") or ""
    m = re.search(r"Patient/([A-Za-z0-9\-.]{1,64})", ref)
    if m:
        fila = db.execute(text("SELECT documento_bidx FROM pacientes WHERE fhir_patient_id = :f AND activo"),
                          {"f": m.group(1)}).first()
        if fila:
            return fila[0]
    ident = sujeto.get("identifier") or {}
    valor = str(ident.get("value") or "").strip()
    if ident.get("system") == fhir_svc.SYS_MRN and _UUID.match(valor):
        fila = db.execute(text("SELECT documento_bidx FROM pacientes WHERE uuid = CAST(:u AS uuid) AND activo"),
                          {"u": valor}).first()
        if fila:
            return fila[0]
    return None


# ------------------------------------------------------- guardar el resultado
ESTADOS_OBS = {"registered": "registered", "preliminary": "preliminary", "final": "final",
               "amended": "amended", "corrected": "amended", "cancelled": "cancelled"}
# Valores críticos por LOINC (además de lo que diga interpretation): (bajo, alto).
CRITICOS = {"2339-0": (54, 400), "2345-7": (54, 400), "15074-8": (54, 400),
            "2823-3": (2.5, 6.0), "718-7": (7.0, None), "59408-5": (88, None), "2708-6": (88, None)}


def _critico(obs: dict, cod: str | None, valor: float | None) -> bool:
    for i in obs.get("interpretation") or []:
        for c in i.get("coding") or []:
            if c.get("code") in ("HH", "LL", "AA", "H>", "L<"):
                return True
    if cod in CRITICOS and valor is not None:
        bajo, alto = CRITICOS[cod]
        return (bajo is not None and valor < bajo) or (alto is not None and valor >= alto)
    return False


def guardar_resultado(db, obs: dict, paciente_id: str, oid: str) -> int | None:
    """
    Inserta la Observation externa en `observaciones` (una sola vez por id de
    FHIR). Se liga al encuentro activo más reciente del paciente, si tiene.
    """
    codigos = (obs.get("code") or {}).get("coding") or []
    loinc = next((c for c in codigos if c.get("system") == fhir_svc.SYS_LOINC), None) or (codigos[0] if codigos else {})
    cod = str(loinc.get("code") or "")[:20] or "sin-codigo"
    display = (loinc.get("display") or LOINC_NOMBRES.get(cod) or (obs.get("code") or {}).get("text") or "")[:150] or None
    cantidad = obs.get("valueQuantity") or {}
    valor = cantidad.get("value")
    try:
        valor = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        valor = None
    texto = None if valor is not None else (str(obs.get("valueString"))[:200] if obs.get("valueString") else None)
    categoria = "laboratory"
    for cat in obs.get("category") or []:
        for c in cat.get("coding") or []:
            if c.get("code") in ("laboratory", "vital-signs"):
                categoria = c["code"]
    fecha = obs.get("effectiveDateTime") or obs.get("issued")
    encuentro = db.execute(text("""
        SELECT id FROM encuentros WHERE paciente_id = :p AND activo AND estado NOT IN ('finished', 'cancelled')
        ORDER BY COALESCE(hora_real_inicio, hora_programada_inicio, created_at) DESC LIMIT 1
    """), {"p": paciente_id}).scalar()
    fila = db.execute(text("""
        INSERT INTO observaciones (encuentro_id, paciente_id, categoria, codigo_loinc, display_loinc,
                                   valor_numerico, valor_texto, unidad_ucum, estado, es_critico, fecha_hora,
                                   fhir_observation_id, origen)
        VALUES (:e, :p, :cat, :cod, :disp, :v, :t, :u, :est, :crit, COALESCE(CAST(:f AS timestamptz), NOW()),
                :oid, 'fhir_externo')
        ON CONFLICT (fhir_observation_id) WHERE origen = 'fhir_externo' DO NOTHING
        RETURNING id
    """), {"e": encuentro, "p": paciente_id, "cat": categoria, "cod": cod, "disp": display, "v": valor,
           "t": texto, "u": str(cantidad.get("unit") or cantidad.get("code") or "")[:20] or None,
           "est": ESTADOS_OBS.get(obs.get("status") or "final", "final"), "crit": _critico(obs, cod, valor),
           "f": fecha, "oid": oid[:64]}).first()
    return fila[0] if fila else None


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
    try:
        with db.begin_nested():
            observacion_id = guardar_resultado(db, obs, paciente_id, oid)
    except Exception:  # noqa: BLE001 -- un dato mal formado no impide avisar
        log.exception("No se pudo guardar la Observation %s", oid)
        observacion_id = None
    destinatarios = _clinicos_responsables(db, paciente_id)
    bandeja.notificar(db, destinatarios, "fhir_observation",
                      mensaje + (" Quedó en la historia del paciente." if observacion_id else ""),
                      paciente_id=paciente_id,
                      datos={"observation_id": oid, "codigo": codigo, "origen": "fhir",
                             "observacion_id": observacion_id})
    registrar(db, None, "paciente", paciente_id, "evento_fhir",
              valor_nuevo={**base, "paciente_id": paciente_id, "notificados": len(destinatarios),
                           "observacion_id": observacion_id})
    return {"resultado": "procesada", "notificados": len(destinatarios), "observacion_id": observacion_id}
