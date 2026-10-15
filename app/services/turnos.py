"""
Turnos de enfermería jefe por área (db/12_turnos.sql).

Siempre hay un jefe de turno por área con camas. Solo él opera el área:
asignar camas, cambiar estados y resolver traslados. Los demás jefes del área
la ven en solo lectura hasta que llegue su turno o cubran el de otro.
Si la tabla aún no existe (migración 12 sin aplicar), no se restringe nada.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

ZONA = "America/Bogota"


def _hay_tabla(db: Session) -> bool:
    return bool(db.execute(text("SELECT to_regclass('public.turnos_area') IS NOT NULL")).scalar())


def turno_en(db: Session, servicio_id: int, cuando: datetime | None = None) -> dict | None:
    """Quién está de turno en el área. Una cobertura posterior gana sobre lo programado."""
    if not _hay_tabla(db):
        return None
    fila = db.execute(text("""
        SELECT t.id, t.usuario_id, u.username, t.inicio, t.fin, t.tipo, t.motivo
        FROM turnos_area t JOIN usuarios u ON u.id = t.usuario_id
        WHERE t.servicio_id = :s AND t.inicio <= :c AND t.fin > :c
        ORDER BY (t.tipo = 'cobertura') DESC, t.id DESC LIMIT 1
    """), {"s": servicio_id, "c": cuando or datetime.now(timezone.utc)}).mappings().first()
    return dict(fila) if fila else None


def programacion(db: Session, servicio_id: int, horas: int = 36) -> list[dict]:
    if not _hay_tabla(db):
        return []
    return [dict(f) for f in db.execute(text("""
        SELECT t.id, t.usuario_id, u.username, t.inicio, t.fin, t.tipo, t.motivo
        FROM turnos_area t JOIN usuarios u ON u.id = t.usuario_id
        WHERE t.servicio_id = :s AND t.fin > NOW() - INTERVAL '6 hours'
          AND t.inicio < NOW() + make_interval(hours => :h)
        ORDER BY t.inicio, t.id
    """), {"s": servicio_id, "h": horas}).mappings()]


def exigir_turno(db: Session, ctx, servicio_id: int | None) -> None:
    """403 si quien opera es un jefe del área que no está de turno."""
    if servicio_id is None or ctx.payload.get("rol") == "admin":
        return
    t = turno_en(db, servicio_id)
    if t is None or t["usuario_id"] == ctx.usuario.id:
        return      # sin programación para esa área, o es quien está de turno
    hasta = t["fin"].astimezone().strftime("%H:%M") if t["fin"] else ""
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        f"No estás de turno. De turno ahora: {t['username']} hasta las {hasta}. "
                        "Puedes ver el área; para operarla, cubre el turno.")
