"""
Bandeja de notificaciones y entrega confiable de eventos (R18, R19).

notificar() hace dos cosas en este orden:
  1. guarda la notificación en la tabla `notificaciones` (dentro de la
     transacción del hecho que la causó), y
  2. deja el evento en cola para el canal en vivo, que SOLO se publica cuando
     esa transacción hace commit (hook after_commit de SQLAlchemy).

Por eso el front nunca recibe un aviso de algo que luego se revirtió, ni
vuelve a pedir su bandeja antes de que el dato exista. Si la transacción se
revierte, la cola se descarta.

Quién puede recibir cada tipo de evento queda fijado en ROLES_POR_TIPO como
defensa en profundidad: aunque un reactor se equivocara de destinatario, un
paciente o un contable jamás recibe un evento clínico.
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Iterable

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.services import eventos

log = logging.getLogger("hsr.bandeja")

# Roles que pueden recibir cada tipo de evento. Un tipo que no está aquí no se
# entrega a nadie.
ROLES_POR_TIPO: dict[str, frozenset[str]] = {
    "remision_nueva":     frozenset({"medico", "especialista", "admin"}),
    "remision_aceptada":  frozenset({"medico", "especialista", "admin"}),
    "remision_rechazada": frozenset({"medico", "especialista", "admin"}),
    "reporte_pendiente":  frozenset({"medico", "especialista"}),
    "alerta_critica":     frozenset({"medico", "especialista", "admin"}),
    "alerta_escalada":    frozenset({"medico", "especialista", "admin"}),
    "fhir_observation":   frozenset({"medico", "especialista"}),
    "factura_creada":     frozenset({"contable", "admin"}),
    "factura_fallida":    frozenset({"contable", "admin"}),
    "cuenta_bloqueada":   frozenset({"admin"}),
}

_RESERVADAS = {"id", "tipo", "mensaje", "fecha", "leida", "paciente_id"}


def _aplanar(datos: dict | None) -> dict:
    return {k: v for k, v in (datos or {}).items() if k not in _RESERVADAS}


def vista(fila) -> dict:
    """Una fila de `notificaciones` como la ve el front y el tester."""
    f = dict(fila)
    fecha = f["fecha"]
    return {
        "id": f["id"], "tipo": f["tipo"], "mensaje": f["mensaje"],
        "leida": bool(f["leida"]), "fecha": fecha.isoformat() if hasattr(fecha, "isoformat") else fecha,
        "paciente_id": (f.get("paciente_id") or None) and f["paciente_id"].strip(),
        **_aplanar(f.get("datos")),
    }


# ----------------------------------------------------------------- entrega
def notificar(db: Session, destinatarios: Iterable[int | None], tipo: str, mensaje: str, *,
              paciente_id: str | None = None, datos: dict | None = None) -> list[dict]:
    """
    Guarda una notificación por destinatario y encola el evento en vivo.
    Devuelve los eventos creados (uno por destinatario que sí puede recibirlos).
    """
    ids = {int(i) for i in destinatarios if i is not None}
    permitidos = ROLES_POR_TIPO.get(tipo)
    if not ids or not permitidos:
        return []
    filas = db.execute(text("""
        SELECT u.id, r.codigo AS rol FROM usuarios u JOIN roles r ON r.id = u.rol_id
        WHERE u.id = ANY(:ids) AND u.activo
    """), {"ids": sorted(ids)}).mappings().all()
    creados: list[dict] = []
    for f in filas:
        if f["rol"] not in permitidos:
            log.warning("Se descartó %s para el usuario %s (rol %s no autorizado)", tipo, f["id"], f["rol"])
            continue
        nueva = db.execute(text("""
            INSERT INTO notificaciones (usuario_id, tipo, mensaje, paciente_id, datos)
            VALUES (:u, :t, :m, :p, CAST(:d AS JSONB))
            RETURNING id, tipo, mensaje, leida, fecha, paciente_id, datos
        """), {"u": f["id"], "t": tipo, "m": mensaje, "p": paciente_id,
               "d": json.dumps(_aplanar(datos), default=str)}).mappings().first()
        ev = vista(nueva)
        db.info.setdefault("eventos_pendientes", []).append((f["id"], ev))
        creados.append(ev)
    return creados


def tras_commit(db: Session, funcion: Callable[[], None]) -> None:
    """Ejecuta `funcion` solo cuando la transacción actual haga commit."""
    db.info.setdefault("tras_commit", []).append(funcion)


def usuarios_con_rol(db: Session, rol: str, excepto: int | None = None) -> list[int]:
    filas = db.execute(text("""
        SELECT u.id FROM usuarios u JOIN roles r ON r.id = u.rol_id
        WHERE r.codigo = :r AND u.activo AND u.id <> COALESCE(:x, -1)
    """), {"r": rol, "x": excepto}).all()
    return [f[0] for f in filas]


# ------------------------------------------------------------------ hooks
@event.listens_for(Session, "after_commit")
def _al_confirmar(sesion: Session) -> None:
    """La transacción quedó guardada: ahora sí se publica y se corren los pendientes."""
    pendientes = sesion.info.pop("eventos_pendientes", [])
    callbacks = sesion.info.pop("tras_commit", [])
    for uid, ev in pendientes:
        eventos.publicar([uid], ev)
    for fn in callbacks:
        try:
            fn()
        except Exception:  # noqa: BLE001 -- el commit ya ocurrió; no se puede tumbar la acción
            log.exception("Falló una tarea posterior al commit")


@event.listens_for(Session, "after_rollback")
def _al_revertir(sesion: Session) -> None:
    sesion.info.pop("eventos_pendientes", None)
    sesion.info.pop("tras_commit", None)
