"""
Servicio de integración BD relacional -> HL7 FHIR R4 (HAPI).

Mapeo implementado
------------------
  pacientes    -> Patient
  encuentros   -> Encounter
  observaciones-> Observation      (códigos LOINC)
  camas        -> Location         (operationalStatus, HL7 v2-0116)
  quirofanos   -> Location
  personal     -> Practitioner
  log_auditoria-> AuditEvent

El recurso Location es el más relevante de esta propuesta: FHIR R4 ya define
`Location.operationalStatus` con el value set v2-0116, cuyos códigos
(U, O, H, C, K, I) corresponden exactamente a los estados de cama y quirófano
que el sistema gestiona. Es decir, el estándar internacional ya contempla
nativamente el problema que abordamos.
"""
from __future__ import annotations

from datetime import date, datetime

import httpx

from app.core.config import get_settings
from app.core.crypto import descifrar

settings = get_settings()

# ---------------------------------------------------------------- sistemas
SYS_LOINC = "http://loinc.org"
SYS_SNOMED = "http://snomed.info/sct"
SYS_ICD10 = "http://hl7.org/fhir/sid/icd-10"
SYS_UCUM = "http://unitsofmeasure.org"
SYS_ACTCODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
SYS_OBS_CAT = "http://terminology.hl7.org/CodeSystem/observation-category"
SYS_LOC_STATUS = "http://terminology.hl7.org/CodeSystem/v2-0116"
SYS_LOC_TYPE = "http://terminology.hl7.org/CodeSystem/location-physical-type"
SYS_ID_TYPE = "http://terminology.hl7.org/CodeSystem/v2-0203"
SYS_HOSPITAL = "http://hsanrafael.co/fhir/identifier"

# ---------------------------------------------------------------- mapeos
# Encuentro.tipo -> Encounter.class (v3-ActCode)
CLASE_ENCUENTRO = {
    "urgencias":        {"code": "EMER",  "display": "emergency"},
    "hospitalizacion":  {"code": "IMP",   "display": "inpatient encounter"},
    "consulta_externa": {"code": "AMB",   "display": "ambulatory"},
    "cirugia":          {"code": "SS",    "display": "short stay"},
}

# Estado interno de cama/quirófano -> Location.operationalStatus (v2-0116)
ESTADO_LOCATION = {
    "disponible":      ("U", "Unoccupied"),
    "reservada":       ("U", "Unoccupied"),
    "ocupada":         ("O", "Occupied"),
    "en_cirugia":      ("O", "Occupied"),
    "en_preparacion":  ("O", "Occupied"),
    "en_proceso_alta": ("O", "Occupied"),
    "en_limpieza":     ("H", "Housekeeping"),
    "bloqueado":       ("C", "Closed"),
    "bloqueada":       ("C", "Closed"),
    "contaminada":     ("K", "Contaminated"),
    "aislamiento":     ("I", "Isolated"),
}

SEXO_FHIR = {"M": "male", "F": "female", "O": "other"}


def _fecha(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


# ==========================================================================
# Constructores de recursos
# ==========================================================================

def paciente_a_fhir(p) -> dict:
    """pacientes -> Patient. Descifra solo lo necesario para el recurso."""
    documento = descifrar(p.documento_cifrado, "pacientes.documento")
    nombre = descifrar(p.nombre_cifrado, "pacientes.nombre")
    apellido = descifrar(p.apellido_cifrado, "pacientes.apellido")
    telefono = descifrar(p.telefono_cifrado, "pacientes.telefono") if p.telefono_cifrado else None

    recurso = {
        "resourceType": "Patient",
        "identifier": [{
            "use": "official",
            "type": {"coding": [{"system": SYS_ID_TYPE, "code": "NI",
                                 "display": "National unique individual identifier"}]},
            "system": SYS_HOSPITAL,
            "value": documento,
        }],
        "active": bool(p.activo),
        "name": [{"use": "official", "family": apellido, "given": [nombre]}],
        "gender": SEXO_FHIR.get(p.sexo, "unknown"),
        "birthDate": _fecha(p.fecha_nacimiento),
    }
    if telefono:
        recurso["telecom"] = [{"system": "phone", "value": telefono, "use": "mobile"}]
    return recurso


def encuentro_a_fhir(e, fhir_patient_id: str | None = None) -> dict:
    clase = CLASE_ENCUENTRO.get(e.tipo, CLASE_ENCUENTRO["hospitalizacion"])

    recurso = {
        "resourceType": "Encounter",
        "identifier": [{"system": SYS_HOSPITAL, "value": str(e.uuid or e.id)}],
        "status": e.estado if e.estado in (
            "planned", "arrived", "triaged", "in-progress",
            "onleave", "finished", "cancelled") else "unknown",
        "class": {"system": SYS_ACTCODE, **clase},
        "subject": {"reference": f"Patient/{fhir_patient_id or e.paciente_id}"},
    }

    # priority: urgencia clínica
    if e.origen == "urgencia":
        recurso["priority"] = {
            "coding": [{"system": SYS_ACTCODE, "code": "UR", "display": "urgent"}]
        }

    inicio = e.hora_real_inicio or e.hora_programada_inicio
    fin = e.hora_real_fin or e.hora_programada_fin
    if inicio:
        recurso["period"] = {"start": _fecha(inicio)}
        if fin:
            recurso["period"]["end"] = _fecha(fin)

    if e.procedimiento and e.procedimiento.codigo_snomed:
        recurso["reasonCode"] = [{
            "coding": [{"system": SYS_SNOMED,
                        "code": e.procedimiento.codigo_snomed,
                        "display": e.procedimiento.nombre}]
        }]
    elif e.procedimiento:
        recurso["reasonCode"] = [{"text": e.procedimiento.nombre}]

    if e.diagnostico:
        recurso.setdefault("reasonCode", []).append({
            "coding": [{"system": SYS_ICD10,
                        "code": e.diagnostico.codigo,
                        "display": e.diagnostico.descripcion}]
        })

    ubicaciones = []
    if e.quirofano_id:
        ubicaciones.append({"location": {"reference": f"Location/qx-{e.quirofano_id}"},
                            "status": "active"})
    if e.cama_id:
        ubicaciones.append({"location": {"reference": f"Location/cama-{e.cama_id}"},
                            "status": "active"})
    if ubicaciones:
        recurso["location"] = ubicaciones

    if e.medico_responsable_id:
        recurso["participant"] = [{
            "type": [{"coding": [{"system": SYS_ACTCODE, "code": "ATND",
                                  "display": "attender"}]}],
            "individual": {"reference": f"Practitioner/{e.medico_responsable_id}"},
        }]
    return recurso


def observacion_a_fhir(o, fhir_patient_id=None, fhir_encounter_id=None) -> dict:
    recurso = {
        "resourceType": "Observation",
        "identifier": [{"system": SYS_HOSPITAL, "value": str(o.uuid or o.id)}],
        "status": o.estado or "final",
        "category": [{
            "coding": [{"system": SYS_OBS_CAT,
                        "code": o.categoria,
                        "display": ("Vital Signs" if o.categoria == "vital-signs"
                                    else "Laboratory")}]
        }],
        "code": {
            "coding": [{"system": SYS_LOINC,
                        "code": o.codigo_loinc,
                        "display": o.display_loinc}],
            "text": o.display_loinc,
        },
        "subject": {"reference": f"Patient/{fhir_patient_id or o.paciente_id}"},
        "encounter": {"reference": f"Encounter/{fhir_encounter_id or o.encuentro_id}"},
        "effectiveDateTime": _fecha(o.fecha_hora),
    }

    if o.valor_numerico is not None:
        recurso["valueQuantity"] = {
            "value": float(o.valor_numerico),
            "unit": o.unidad_ucum,
            "system": SYS_UCUM,
            "code": o.unidad_ucum,
        }
    elif o.valor_texto:
        recurso["valueString"] = o.valor_texto

    if o.es_critico:
        recurso["interpretation"] = [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code": "AA", "display": "Critical abnormal",
            }]
        }]
    return recurso


def cama_a_fhir(c) -> dict:
    """
    camas -> Location.
    El mapeo estrella: Location.operationalStatus (v2-0116) equivale
    exactamente a nuestros estados de cama.
    """
    codigo, display = ESTADO_LOCATION.get(c.estado, ("U", "Unoccupied"))
    recurso = {
        "resourceType": "Location",
        "identifier": [{"system": SYS_HOSPITAL, "value": c.codigo}],
        "status": "active" if c.activo else "inactive",
        "operationalStatus": {"system": SYS_LOC_STATUS,
                              "code": codigo, "display": display},
        "name": f"Cama {c.codigo}",
        "mode": "instance",
        "physicalType": {"coding": [{"system": SYS_LOC_TYPE,
                                     "code": "bd", "display": "Bed"}]},
    }
    if c.tipo_cama and c.tipo_cama.codigo_snomed:
        recurso["type"] = [{
            "coding": [{"system": SYS_SNOMED,
                        "code": c.tipo_cama.codigo_snomed,
                        "display": c.tipo_cama.nombre}]
        }]
    return recurso


def quirofano_a_fhir(q) -> dict:
    codigo, display = ESTADO_LOCATION.get(q.estado, ("U", "Unoccupied"))
    return {
        "resourceType": "Location",
        "identifier": [{"system": SYS_HOSPITAL, "value": q.codigo}],
        "status": "active" if q.activo else "inactive",
        "operationalStatus": {"system": SYS_LOC_STATUS,
                              "code": codigo, "display": display},
        "name": q.nombre or f"Quirófano {q.codigo}",
        "mode": "instance",
        "physicalType": {"coding": [{"system": SYS_LOC_TYPE,
                                     "code": "ro", "display": "Room"}]},
    }


def personal_a_fhir(p) -> dict:
    nombre = descifrar(p.nombre_cifrado, "personal.nombre")
    apellido = descifrar(p.apellido_cifrado, "personal.apellido")
    return {
        "resourceType": "Practitioner",
        "identifier": [{"system": SYS_HOSPITAL, "value": str(p.uuid or p.id)}],
        "active": bool(p.activo),
        "name": [{"use": "official", "family": apellido, "given": [nombre]}],
    }


def auditoria_a_fhir(log) -> dict:
    """log_auditoria -> AuditEvent. Diferenciador: pocos equipos lo mapean."""
    accion = {"create": "C", "read": "R", "update": "U",
              "soft_delete": "D", "restore": "U", "login": "E"}.get(log.operacion, "E")
    return {
        "resourceType": "AuditEvent",
        "type": {"system": "http://terminology.hl7.org/CodeSystem/audit-event-type",
                 "code": "rest", "display": "RESTful Operation"},
        "action": accion,
        "recorded": _fecha(log.timestamp),
        "outcome": "0" if log.resultado == "exito" else "4",
        "agent": [{
            "who": {"reference": f"Practitioner/{log.usuario_id}"},
            "requestor": True,
            "network": {"address": str(log.ip_origen or ""), "type": "2"},
        }],
        "source": {"observer": {"display": "API Hospital San Rafael"}},
        "entity": [{
            "what": {"reference": f"{log.entidad_tipo}/{log.entidad_id}"},
            "name": log.entidad_tipo,
        }],
    }


# ==========================================================================
# Cliente HAPI FHIR
# ==========================================================================

class ClienteFHIR:
    def __init__(self, base_url: str | None = None):
        self.base = (base_url or settings.fhir_base_url).rstrip("/")
        self.timeout = settings.fhir_timeout

    def _headers(self) -> dict:
        return {"Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json"}

    def crear(self, tipo: str, recurso: dict) -> dict:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.post(f"{self.base}/{tipo}", json=recurso, headers=self._headers())
            r.raise_for_status()
            return r.json()

    def actualizar(self, tipo: str, fhir_id: str, recurso: dict) -> dict:
        recurso["id"] = fhir_id
        with httpx.Client(timeout=self.timeout) as c:
            r = c.put(f"{self.base}/{tipo}/{fhir_id}", json=recurso,
                      headers=self._headers())
            r.raise_for_status()
            return r.json()

    def leer(self, tipo: str, fhir_id: str) -> dict:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(f"{self.base}/{tipo}/{fhir_id}", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def buscar(self, tipo: str, **params) -> dict:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(f"{self.base}/{tipo}", params=params, headers=self._headers())
            r.raise_for_status()
            return r.json()

    def historial(self, tipo: str, fhir_id: str) -> dict:
        """Versionado nativo de FHIR: complementa nuestro soft edit."""
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(f"{self.base}/{tipo}/{fhir_id}/_history",
                      headers=self._headers())
            r.raise_for_status()
            return r.json()

    def transaccion(self, entradas: list[dict]) -> dict:
        """Bundle transaccional: varios recursos en una operación atómica."""
        bundle = {"resourceType": "Bundle", "type": "transaction", "entry": entradas}
        with httpx.Client(timeout=self.timeout) as c:
            r = c.post(self.base, json=bundle, headers=self._headers())
            r.raise_for_status()
            return r.json()

    def capabilities(self) -> dict:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(f"{self.base}/metadata", headers=self._headers())
            r.raise_for_status()
            return r.json()
