"""
Puerta de acceso al servidor FHIR expuesto en /fhir.

HAPI FHIR no tiene autenticación propia y guarda datos clínicos y el nombre
del paciente. nginx consulta esta ruta (auth_request) antes de dejar pasar
cada petición a /fhir:

  · GET  /fhir/metadata ...... público (CapabilityStatement, sin datos clínicos).
  · Lecturas (GET/HEAD) ...... token de la API con permiso fhir:read.
  · Escrituras ............... token con fhir:sync (cuenta de integración o admin).
                               Un laboratorio externo publica sus resultados
                               (Observation, R21) con la cuenta de integración.
  · DELETE ................... nunca desde afuera.

Antes la búsqueda de un paciente por cédula y la publicación de una
Observation eran públicas (para el tester). Se cerraron: con solo conocer una
cédula, cualquiera podía sacar los datos del paciente o meterle resultados
falsos a su historia (ahora los resultados externos se guardan, ver
app/services/fhir_reactivo.py). Además el Patient ya no lleva la cédula.

La API habla con HAPI por la red interna (hapi-fhir:8080), sin pasar por aquí.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.core.security import decodificar_token, tiene_permiso

router = APIRouter(prefix="/interno", include_in_schema=False)


def decidir(metodo: str, ruta: str, autorizacion: str | None) -> int:
    """Código que nginx devuelve: 204 deja pasar; 401/403 corta."""
    metodo = metodo.upper()
    ruta = ruta.partition("?")[0]
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
