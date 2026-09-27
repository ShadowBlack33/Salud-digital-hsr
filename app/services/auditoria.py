"""
Auditoría y operaciones "soft".

La tabla log_auditoria es append-only (protegida por trigger en la BD):
ni siquiera un admin puede alterarla. Eso es lo que la hace válida como
evidencia de trazabilidad.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import HistorialCambio, LogAuditoria

# Campos que NUNCA se escriben en claro en la auditoría ni en el historial.
CAMPOS_SENSIBLES = {
    "documento_cifrado", "nombre_cifrado", "apellido_cifrado",
    "telefono_cifrado", "email_cifrado", "direccion_cifrada",
    "documento_bidx", "password_hash", "mfa_secret_cifrado",
    "registro_profesional_cifrado",
}


def _serializar(valor):
    """Convierte a algo que JSONB acepte. UUID y date no lo son de fábrica."""
    import uuid as _uuid
    from datetime import date as _date

    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, bytes):
        return "<cifrado>"
    if isinstance(valor, (datetime, _date)):
        return valor.isoformat()
    if isinstance(valor, _uuid.UUID):
        return str(valor)
    if isinstance(valor, Decimal):
        return float(valor)
    return str(valor)


def snapshot(obj, incluir_sensibles: bool = False) -> dict:
    """Captura el estado de un registro, enmascarando lo sensible."""
    if obj is None:
        return {}
    datos = {}
    for col in obj.__table__.columns:
        nombre = col.name
        if nombre in CAMPOS_SENSIBLES and not incluir_sensibles:
            datos[nombre] = "<protegido>"
        else:
            datos[nombre] = _serializar(getattr(obj, nombre, None))
    return datos


def _ip_valida(request: Request | None) -> str | None:
    """
    La columna es de tipo INET: un valor no-IP aborta la transacción.
    Detrás de un proxy o en clientes de prueba el host puede no ser una IP,
    así que se valida antes de persistir.
    """
    if request is None or request.client is None:
        return None
    import ipaddress
    host = request.client.host
    # Respetar X-Forwarded-For si el despliegue está detrás de proxy
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        host = reenviada.split(",")[0].strip()
    try:
        ipaddress.ip_address(host)
        return host
    except (ValueError, TypeError):
        return None


def registrar(db: Session, usuario, entidad_tipo: str, entidad_id: int | None,
              operacion: str, valor_anterior: dict | None = None,
              valor_nuevo: dict | None = None, resultado: str = "exito",
              request: Request | None = None) -> LogAuditoria:
    """Escribe una entrada en el log de auditoría."""
    log = LogAuditoria(
        usuario_id=getattr(usuario, "id", None),
        rol_codigo=getattr(getattr(usuario, "rol", None), "codigo", None),
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        operacion=operacion,
        resultado=resultado,
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
        ip_origen=_ip_valida(request),
        user_agent=request.headers.get("user-agent") if request else None,
        endpoint=f"{request.method} {request.url.path}" if request else None,
    )
    db.add(log)
    return log


# --------------------------------------------------------------------------
# Operaciones soft
# --------------------------------------------------------------------------

def soft_delete(db: Session, obj, usuario, entidad_tipo: str,
                request: Request | None = None):
    """
    Marca el registro como inactivo SIN borrarlo físicamente.
    El dato permanece para trazabilidad y para que un admin pueda restaurarlo.
    """
    antes = snapshot(obj)
    obj.activo = False
    obj.deleted_at = datetime.now(timezone.utc)
    obj.deleted_by = usuario.id
    registrar(db, usuario, entidad_tipo, obj.id, "soft_delete",
              valor_anterior=antes, valor_nuevo=snapshot(obj), request=request)
    return obj


def restaurar(db: Session, obj, usuario, entidad_tipo: str,
              request: Request | None = None):
    """
    Revierte un soft delete. Reservado exclusivamente al rol admin
    (la restricción se aplica en el endpoint, vía permiso ':restore').
    """
    antes = snapshot(obj)
    obj.activo = True
    obj.deleted_at = None
    obj.deleted_by = None
    registrar(db, usuario, entidad_tipo, obj.id, "restore",
              valor_anterior=antes, valor_nuevo=snapshot(obj), request=request)
    return obj


def soft_edit(db: Session, obj, cambios: dict, usuario, entidad_tipo: str,
              request: Request | None = None):
    """
    Actualiza conservando el valor anterior en historial_cambios,
    en lugar de sobrescribirlo. Cada campo modificado genera una fila.
    """
    antes = snapshot(obj)

    version_actual = (
        db.query(HistorialCambio)
        .filter(HistorialCambio.entidad_tipo == entidad_tipo,
                HistorialCambio.entidad_id == obj.id)
        .count()
    )
    nueva_version = version_actual + 1

    for campo, valor_nuevo in cambios.items():
        if not hasattr(obj, campo):
            continue
        valor_anterior = getattr(obj, campo)
        if valor_anterior == valor_nuevo:
            continue

        es_sensible = campo in CAMPOS_SENSIBLES
        db.add(HistorialCambio(
            entidad_tipo=entidad_tipo,
            entidad_id=obj.id,
            version=nueva_version,
            campo=campo,
            # Si el campo es sensible se guarda el ciphertext, nunca el claro
            valor_anterior=("<cifrado>" if es_sensible
                            else str(_serializar(valor_anterior))),
            valor_nuevo=("<cifrado>" if es_sensible
                         else str(_serializar(valor_nuevo))),
            era_cifrado=es_sensible,
            usuario_id=usuario.id,
        ))
        setattr(obj, campo, valor_nuevo)

    if hasattr(obj, "updated_at"):
        obj.updated_at = datetime.now(timezone.utc)

    registrar(db, usuario, entidad_tipo, obj.id, "update",
              valor_anterior=antes, valor_nuevo=snapshot(obj), request=request)
    return obj
