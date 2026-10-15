"""
Alertas críticas con reconocimiento y escalamiento (R20).

  GET  /alertas                     {id, paciente_id, nivel, estado, ...}; ?estado=activa|reconocida
  POST /alertas/{id}/reconocer      {nota} -> 'reconocida' (con usuario, hora y nota)

Nacen en POST /ia/analizar cuando el modelo marca el caso como crítico
(app/api/ia.py: crear_alerta_critica), dirigidas al clínico que pidió el
análisis. Solo medico y especialista las ven y las reconocen (el admin las ve
todas por el escalamiento); paciente y contable reciben 403.

Escalamiento: una tarea de fondo revisa cada 30 s las alertas activas más
viejas que ALERTA_ESCALAMIENTO_MINUTOS (5 por defecto). Marca escalada_at,
audita y avisa al admin y a otro clínico del paciente (evento alerta_escalada).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import ContextoAcceso, RequierePermiso, SessionLocal, get_db
from app.models import Paciente
from app.services import reactores
from app.services.auditoria import registrar

router = APIRouter(tags=["Alertas críticas"])
settings = get_settings()
log = logging.getLogger("hsr.alertas")

INTERVALO_REVISION_S = 30


class Reconocer(BaseModel):
    nota: str = Field(..., min_length=3, max_length=1000)


class _Fila:
    def __init__(self, d: dict):
        self.__dict__.update(d)


def _vista(a: dict, db: Session) -> dict:
    from app.api.ia import nombre_paciente   # evita import circular al cargar routers
    p = db.get(Paciente, a["paciente_id"]) if a["paciente_id"] else None
    escala_en = None
    if a["estado"] == "activa" and a["escalada_at"] is None:
        escala_en = a["created_at"] + timedelta(minutes=settings.alerta_escalamiento_minutos)
    return {
        "id": a["id"], "paciente_id": a["paciente_id"].strip() if a["paciente_id"] else None,
        "paciente_nombre": nombre_paciente(p),
        "nivel": a["severidad"], "estado": a["estado"], "tipo": a["tipo"],
        "titulo": a["titulo"], "mensaje": a["mensaje"], "reporte_id": a["reporte_id"],
        "dirigida_a_usuario": a["dirigida_a_usuario"],
        "created_at": a["created_at"], "escala_en": escala_en, "escalada_at": a["escalada_at"],
        "reconocida_por": a["reconocida_por"], "reconocida_at": a["reconocida_at"],
        "nota_reconocimiento": a["nota_reconocimiento"],
    }


@router.get("/alertas", summary="Alertas críticas")
def listar(estado: str | None = Query(None, pattern="^(activa|reconocida)$"),
           ctx: ContextoAcceso = Depends(RequierePermiso("alerta", "read")),
           db: Session = Depends(get_db)):
    filtros, params = ["reporte_id IS NOT NULL"], {}
    if ctx.alcance != "all":
        filtros.append("dirigida_a_usuario = :u")
        params["u"] = ctx.usuario.id
    if estado:
        filtros.append("estado = :e")
        params["e"] = estado
    filas = db.execute(text(f"""
        SELECT * FROM alertas WHERE {' AND '.join(filtros)}
        ORDER BY (estado = 'activa') DESC, created_at DESC LIMIT 200
    """), params).mappings().all()
    return {"alertas": [_vista(dict(a), db) for a in filas]}


@router.post("/alertas/{alerta_id}/reconocer", summary="Reconocer una alerta crítica con una nota")
def reconocer(alerta_id: int, datos: Reconocer, request: Request,
              ctx: ContextoAcceso = Depends(RequierePermiso("alerta", "update")),
              db: Session = Depends(get_db)):
    a = db.execute(text("SELECT * FROM alertas WHERE id = :i AND reporte_id IS NOT NULL"),
                   {"i": alerta_id}).mappings().first()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
    # Puede reconocerla el clínico al que va dirigida, o cualquier clínico que
    # tenga al paciente a su cargo (por ejemplo, el que recibió el escalamiento).
    if a["dirigida_a_usuario"] != ctx.usuario.id and not ctx.es_paciente_asignado(a["paciente_id"]):
        registrar(db, ctx.usuario, "alerta", alerta_id, "reconocer", resultado="denegado", request=request)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta alerta no está dirigida a usted")
    fila = db.execute(text("""
        UPDATE alertas SET estado = 'reconocida', nota_reconocimiento = :n,
               reconocida_por = :u, reconocida_at = :t, resuelta_at = :t, resuelta_por = :u
        WHERE id = :i AND estado = 'activa' RETURNING *
    """), {"n": datos.nota.strip(), "u": ctx.usuario.id, "t": datetime.now(timezone.utc),
           "i": alerta_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "La alerta ya fue reconocida")
    registrar(db, ctx.usuario, "alerta", alerta_id, "reconocer",
              valor_anterior={"estado": "activa"},
              valor_nuevo={"estado": "reconocida", "paciente_id": a["paciente_id"],
                           "reporte_id": a["reporte_id"], "con_nota": True}, request=request)
    db.commit()
    return _vista(dict(fila), db)


# ---------------------------------------------------------------- escalamiento
def escalar_vencidas() -> int:
    """Escala las alertas activas sin reconocer más viejas que N minutos. Devuelve cuántas."""
    limite = datetime.now(timezone.utc) - timedelta(minutes=settings.alerta_escalamiento_minutos)
    with SessionLocal() as db:
        vencidas = db.execute(text("""
            SELECT * FROM alertas
            WHERE estado = 'activa' AND escalada_at IS NULL AND reporte_id IS NOT NULL
              AND created_at < :limite
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
        """), {"limite": limite}).mappings().all()
        for a in vencidas:
            admins = [u for (u,) in db.execute(text("""
                SELECT u.id FROM usuarios u JOIN roles r ON r.id = u.rol_id
                WHERE r.codigo = 'admin' AND u.activo"""))]
            # "Otro clínico": un médico de un encuentro activo del paciente, distinto del destinatario.
            otros = [u for (u,) in db.execute(text("""
                SELECT DISTINCT u.id FROM encuentros e
                JOIN usuarios u ON u.personal_id = e.medico_responsable_id AND u.activo
                JOIN roles r ON r.id = u.rol_id AND r.codigo IN ('medico', 'especialista')
                WHERE e.paciente_id = :p AND e.activo AND u.id <> :yo
                LIMIT 1"""), {"p": a["paciente_id"], "yo": a["dirigida_a_usuario"] or -1})]
            db.execute(text("UPDATE alertas SET escalada_at = NOW() WHERE id = :i"), {"i": a["id"]})
            registrar(db, None, "alerta", a["id"], "alerta_escalada",
                      valor_nuevo={"paciente_id": a["paciente_id"], "reporte_id": a["reporte_id"],
                                   "minutos_sin_reconocer": settings.alerta_escalamiento_minutos,
                                   "avisados": admins + otros})
            reactor = getattr(reactores, "al_alerta_escalada", None)
            if reactor:
                try:
                    reactor(db, _Fila({**dict(a), "tipo": "alerta_escalada", "destinatarios": admins + otros}))
                except Exception:  # noqa: BLE001
                    log.exception("Falló el aviso de escalamiento de la alerta %s", a["id"])
        db.commit()
        return len(vencidas)


async def _bucle_escalamiento() -> None:
    while True:
        try:
            n = await asyncio.to_thread(escalar_vencidas)
            if n:
                log.info("Alertas escaladas: %s", n)
        except Exception:  # noqa: BLE001 -- la tarea nunca debe morir
            log.exception("Error revisando alertas para escalar")
        await asyncio.sleep(INTERVALO_REVISION_S)


def registrar_escalamiento(app: FastAPI) -> None:
    """Arranca la tarea de fondo con la API (se llama desde app/main.py)."""
    @app.on_event("startup")
    async def _iniciar() -> None:  # noqa: RUF029
        app.state.tarea_escalamiento = asyncio.create_task(_bucle_escalamiento())
