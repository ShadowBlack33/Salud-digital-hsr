"""
Puerta de acceso al servidor FHIR expuesto en /fhir.

HAPI FHIR no tiene autenticación propia y guarda nombre, documento y teléfono
del paciente. nginx consulta esta ruta (auth_request) antes de dejar pasar
cada petición a /fhir:

  · POST /fhir/Observation ... público: es lo que el tester y un laboratorio
                               externo publican para disparar la reacción (R21).
                               nginx limita tasa y tamaño del cuerpo.
  · GET  /fhir/metadata ...... público (CapabilityStatement, sin datos clínicos).
  · GET  /fhir/Patient?identifier=<valor exacto>  público (R15: el tester busca
                               el paciente creado "por su identificador"). Solo
                               esa búsqueda exacta: listar o recorrer pacientes
                               sigue cerrado, y hay que conocer el identificador.
  · Lecturas (GET/HEAD) ...... token de la API con permiso fhir:read.
  · Otras escrituras ......... token con fhir:sync (cuenta de integración o admin).
  · DELETE ................... nunca desde afuera.

La API habla con HAPI por la red interna (hapi-fhir:8080), sin pasar por aquí.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs

from fastapi import APIRouter, Request, Response, status

from app.core.security import decodificar_token, tiene_permiso

router = APIRouter(prefix="/interno", include_in_schema=False)

_OBSERVATION = re.compile(r"^/fhir/Observation/?$")


def _busqueda_exacta(consulta: str) -> bool:
    """identifier=<valor> y nada más (se tolera _format); sin modificadores ni comodines."""
    q = parse_qs(consulta, keep_blank_values=True)
    claves = set(q) - {"_format"}
    if claves != {"identifier"} or len(q["identifier"]) != 1:
        return False
    valor = q["identifier"][0]
    return bool(valor) and len(valor) <= 200 and not any(c in valor for c in "*,%")


def decidir(metodo: str, ruta: str, autorizacion: str | None) -> int:
    """Código que nginx devuelve: 204 deja pasar; 401/403 corta."""
    metodo = metodo.upper()
    ruta, _, consulta = ruta.partition("?")
    if metodo in ("GET", "HEAD") and ruta.rstrip("/") == "/fhir/Patient" and _busqueda_exacta(consulta):
        return status.HTTP_204_NO_CONTENT
    if metodo == "POST" and _OBSERVATION.match(ruta):
        return status.HTTP_204_NO_CONTENT
    if metodo in ("GET", "HEAD") and ruta.rstrip("/") == "/fhir/metadata":
        return status.HTTP_204_NO_CONTENT
    if metodo == "DELETE":
        return status.HTTP_403_FORBIDDEN
    if not autorizacion or not autorizacion.lower().startswith("bearer "):
        return status.HTTP_401_UNAUTHORIZED
    try:
        payload = decodificar_token(autorizacion.split(" ", 1)[1].strip())
    except ValueError:
        return status.HTTP_401_UNAUTHORIZED
    if payload.get("type") != "access":
        return status.HTTP_401_UNAUTHORIZED
    permisos = payload.get("permisos", [])
    if metodo in ("GET", "HEAD"):
        ok = tiene_permiso(permisos, "fhir", "read")
    else:
        ok = "fhir:sync:write" in permisos
    return status.HTTP_204_NO_CONTENT if ok else status.HTTP_403_FORBIDDEN


@router.get("/puerta-fhir")
def puerta_fhir(request: Request) -> Response:
    codigo = decidir(request.headers.get("x-original-method", "GET"),
                     request.headers.get("x-original-uri", "/"),
                     request.headers.get("authorization"))
    return Response(status_code=codigo)
