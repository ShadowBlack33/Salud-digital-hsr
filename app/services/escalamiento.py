"""
Escalamiento de alertas críticas no reconocidas (R20, punto 4).

Una alerta `activa` que lleva ESCALAMIENTO_MINUTOS sin que un clínico la
reconozca se escala: se avisa a todos los admin (evento `alerta_escalada`, por
la bandeja y el canal en vivo) y queda en la auditoría. Se hace en el
SERVIDOR: si el médico cierra la pestaña o el front no está abierto, el
escalamiento ocurre igual (la cuenta regresiva del front es solo una guía).

Una alerta se escala una sola vez: el UPDATE ... WHERE escalada_at IS NULL es
atómico, así que aunque haya dos revisiones simultáneas (o dos réplicas), solo
una gana la fila y avisa.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from app.core.config import get_settings
from app.services import bandeja
from app.services.auditoria import registrar

log = logging.getLogger("hsr.escalamiento")
settings = get_settings()

REVISAR_CADA_SEGUNDOS = 20


def escalar_vencidas() -> int:
    """Escala las alertas activas vencidas. Devuelve cuántas escaló."""
    from app.core.deps import SessionLocal

    with SessionLocal() as db:
        vencidas = db.execute(text("""
            UPDATE alertas_criticas SET escalada_at = NOW()
            WHERE estado = 'activa' AND escalada_at IS NULL
              AND creada_at < NOW() - (:m * INTERVAL '1 minute')
            RETURNING id, paciente_id, usuario_id, nivel
        """), {"m": settings.escalamiento_minutos}).mappings().all()
        if not vencidas:
            db.rollback()
            return 0
        admins = bandeja.usuarios_con_rol(db, "admin")
        for a in vencidas:
            registrar(db, None, "alerta", a["id"], "escalar",
                      valor_nuevo={"paciente_id": a["paciente_id"].strip(), "responsable_id": a["usuario_id"],
                                   "nivel": a["nivel"], "minutos_sin_reconocer": settings.escalamiento_minutos})
            bandeja.notificar(
                db, admins, "alerta_escalada",
                f"La alerta crítica n.º {a['id']} lleva {settings.escalamiento_minutos} min sin reconocer. "
                "Requiere atención del clínico responsable.",
                paciente_id=a["paciente_id"],
                datos={"alerta_id": a["id"], "nivel": a["nivel"], "responsable_id": a["usuario_id"]})
        db.commit()
        return len(vencidas)


async def vigilar() -> None:
    """Tarea de fondo: revisa periódicamente las alertas vencidas."""
    log.info("Escalamiento de alertas activo (%s min)", settings.escalamiento_minutos)
    while True:
        try:
            await run_in_threadpool(escalar_vencidas)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 -- p. ej. la migración 13 aún no se aplicó
            log.warning("No se pudo revisar el escalamiento de alertas: %s", type(e).__name__)
        await asyncio.sleep(REVISAR_CADA_SEGUNDOS)
