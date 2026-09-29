"""
API de Coordinación de Capacidad Quirúrgica — Hospital San Rafael

Documentación interactiva (Swagger): /docs
Esquema OpenAPI:                     /openapi.json
"""
from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, clinico, imaging, pacientes, recursos
from app.core.config import get_settings

settings = get_settings()

DESCRIPCION = """
API del sistema de coordinación en tiempo real de **quirófanos, camas y urgencias**.

### Seguridad
* Autenticación JWT (access 15 min + refresh rotativo 7 días)
* RBAC granular con permisos en base de datos (14 roles)
* Autorización en **dos niveles**: por endpoint y por registro
* Datos identificatorios cifrados con **AES-256-GCM**
* Búsqueda sobre datos cifrados mediante **blind index** (HMAC-SHA256)
* Contraseñas con **Argon2id**

### Trazabilidad
* `soft delete` — marca inactivo, no borra
* `soft edit` — conserva el valor anterior en historial
* `restaurar` — exclusivo del rol admin
* Log de auditoría **append-only** (protegido por trigger en la BD)

### Interoperabilidad
Exposición como **HL7 FHIR R4**: `Patient`, `Encounter`, `Observation`,
`Location`, `Practitioner` y `AuditEvent`.
El estado de camas y quirófanos usa `Location.operationalStatus`
(value set HL7 v2-0116), que el estándar ya define para este fin.
"""

app = FastAPI(
    title=settings.app_nombre,
    version=settings.app_version,
    description=DESCRIPCION,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Equipo Salud Digital — Hospital San Rafael"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origenes,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    """Cabeceras de seguridad y medición de latencia."""
    inicio = time.perf_counter()
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    respuesta.headers["X-Tiempo-ms"] = f"{(time.perf_counter() - inicio) * 1000:.1f}"
    if settings.entorno == "produccion":
        respuesta.headers["Strict-Transport-Security"] = \
            "max-age=31536000; includeSubDomains"
    return respuesta


@app.exception_handler(Exception)
async def error_no_controlado(request: Request, exc: Exception):
    """
    Nunca se filtra la traza al cliente: podría revelar estructura interna
    o datos de pacientes.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
    )


app.include_router(auth.router)
app.include_router(pacientes.router)
app.include_router(clinico.router)
app.include_router(recursos.router)
app.include_router(recursos.fhir_router)
app.include_router(recursos.audit_router)
app.include_router(recursos.analitica_router)
app.include_router(imaging.router)


@app.get("/", tags=["Sistema"], summary="Información de la API")
def raiz():
    return {
        "nombre": settings.app_nombre,
        "version": settings.app_version,
        "entorno": settings.entorno,
        "documentacion": "/docs",
        "salud": "/salud",
    }


@app.get("/salud", tags=["Sistema"], summary="Health check")
def salud():
    from sqlalchemy import text
    from app.core.deps import SessionLocal

    estado_bd = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as e:
        estado_bd = f"error: {type(e).__name__}"

    from app.services import pacs
    estado_pacs = "ok" if pacs.is_alive() else "no disponible"

    return {"api": "ok", "base_datos": estado_bd,
            "servidor_fhir": settings.fhir_base_url,
            "pacs": estado_pacs}
