"""
Alertas críticas con reconocimiento y escalamiento (R20).

  GET  /alertas                     {id, paciente_id, nivel, estado, ...}; ?estado=activa|reconocida
  POST /alertas/{id}/reconocer      {nota} -> 'reconocida' (con usuario, hora y nota)
  GET  /alertas/sin-atender         contador por médico de las alertas activas (sin datos
                                    del paciente). Coordinador y admin (alerta:supervisar).

Nacen en POST /ia/analizar cuando el modelo marca el caso como crítico
(app/api/ia.py: crear_alerta_critica), dirigidas al clínico que pidió el
análisis. Solo medico y especialista las ven y las reconocen (el admin puede
verlas todas); paciente y contable reciben 403.

Escalamiento: una tarea de fondo revisa cada 30 s las alertas activas más
viejas que ALERTA_ESCALAMIENTO_MINUTOS (5 por defecto). Marca escalada_at,
audita y avisa a los OTROS médicos y especialistas a cargo del paciente, que
son quienes pueden resolverla (evento alerta_escalada). No se escala al admin:
no atiende pacientes. Quien supervisa (coordinador, admin) ve el contador de
/alertas/sin-atender, que dice qué médico tiene alertas sin atender y hace cuánto.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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


@router.get("/alertas/sin-atender", summary="Alertas críticas sin atender, por médico (sin datos del paciente)")
def sin_atender(ctx: ContextoAcceso = Depends(RequierePermiso("alerta", "supervisar")),
                db: Session = Depends(get_db)):
    limite = datetime.now(timezone.utc) - timedelta(minutes=settings.alerta_escalamiento_minutos)
    filas = db.execute(text("""
        SELECT a.dirigida_a_usuario AS usuario_id, u.username, r.codigo AS rol, u.personal_id,
               COUNT(*) AS sin_atender,
               COUNT(*) FILTER (WHERE a.created_at < :limite) AS vencidas,
               MIN(a.created_at) AS mas_antigua
        FROM alertas a
        LEFT JOIN usuarios u ON u.id = a.dirigida_a_usuario
        LEFT JOIN roles r ON r.id = u.rol_id
        WHERE a.estado = 'activa' AND a.dirigida_a_usuario IS NOT NULL
        GROUP BY a.dirigida_a_usuario, u.username, r.codigo, u.personal_id
        ORDER BY vencidas DESC, sin_atender DESC, mas_antigua
    """), {"limite": limite}).mappings().all()
    from app.api.remisiones import _nombre_personal   # noqa: PLC0415 -- evita import circular
    ahora = datetime.now(timezone.utc)
    medicos = [{
        "usuario_id": f["usuario_id"], "usuario": f["username"], "rol": f["rol"],
        "nombre": _nombre_personal(db, f["personal_id"]) or f["username"],
        "sin_atender": f["sin_atender"], "vencidas": f["vencidas"],
        "minutos_mas_antigua": int((ahora - f["mas_antigua"]).total_seconds() // 60),
    } for f in filas]
    return {"total": sum(m["sin_atender"] for m in medicos),
            "vencidas": sum(m["vencidas"] for m in medicos),
            "minutos_para_vencer": settings.alerta_escalamiento_minutos,
            "medicos": medicos}


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
        from app.services.fhir_reactivo import _clinicos_responsables   # noqa: PLC0415
        for a in vencidas:
            # Los otros médicos y especialistas a cargo del paciente (encuentro activo,
            # remisión abierta o quien lo registró): pueden reconocerla y actuar.
            otros = [u for u in _clinicos_responsables(db, a["paciente_id"]) if u != a["dirigida_a_usuario"]]
            db.execute(text("UPDATE alertas SET escalada_at = NOW() WHERE id = :i"), {"i": a["id"]})
            registrar(db, None, "alerta", a["id"], "alerta_escalada",
                      valor_nuevo={"paciente_id": a["paciente_id"], "reporte_id": a["reporte_id"],
                                   "minutos_sin_reconocer": settings.alerta_escalamiento_minutos,
                                   "avisados": otros})
            reactor = getattr(reactores, "al_alerta_escalada", None)
            if reactor:
                try:
                    reactor(db, _Fila({**dict(a), "tipo": "alerta_escalada", "destinatarios": otros}))
                except Exception:  # noqa: BLE001
                    log.exception("Falló el aviso de escalamiento de la alerta %s", a["id"])
        db.commit()
        return len(vencidas)


async def bucle_escalamiento() -> None:
    """Revisa cada 30 s. Lo arranca el lifespan de app/main.py (ciclo_de_vida)."""
    while True:
        try:
            n = await asyncio.to_thread(escalar_vencidas)
            if n:
                log.info("Alertas escaladas: %s", n)
        except Exception:  # noqa: BLE001 -- la tarea nunca debe morir
            log.exception("Error revisando alertas para escalar")
        await asyncio.sleep(INTERVALO_REVISION_S)

