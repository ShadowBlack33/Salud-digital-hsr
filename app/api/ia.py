"""
Análisis de IA con aprobación clínica ("soft put", R10) y capa de datos hacia
el modelo (R12).

  POST /ia/analizar                 arma el payload seudonimizado, llama al servicio ml y
                                    crea el reporte 'pendiente' (y la alerta si es crítico)
  GET  /ia/reportes                 lista (?paciente_id=, ?estado=)
  GET  /ia/reportes/{id}            un reporte
  GET  /ia/reportes/{id}/payload    el JSON EXACTO que recibió el modelo
  POST /ia/reportes/{id}/aprobar    {observaciones}  -> entra a la historia clínica
  POST /ia/reportes/{id}/rechazar   {observaciones}  -> NO se borra: queda como evidencia

El reporte nace 'pendiente' y no forma parte de la historia hasta que un medico
o especialista lo aprueba. Solo se pasa de 'pendiente' a 'aprobado' o
'rechazado' (409 en cualquier otro caso); la base también lo impide con un
trigger (db/13_ia.sql). paciente y contable reciben 403 al aprobar.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, column, select, table, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import descifrar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Paciente
from app.services import reactores
from app.services import seudonimizacion as seudo
from app.services.auditoria import registrar

router = APIRouter(prefix="/ia", tags=["Inteligencia artificial"])
settings = get_settings()

_reportes = table("reportes_ia", column("id"), column("paciente_id"), column("estado"),
                  column("created_at"), column("creado_por"))


class Analizar(BaseModel):
    paciente_id: str = Field(..., min_length=1, max_length=64)


class Decision(BaseModel):
    observaciones: str | None = Field(None, max_length=2000)


class _Fila:
    """Objeto simple para los reactores (tienen .id y los demás campos como atributos)."""
    def __init__(self, d: dict):
        self.__dict__.update(d)


# ---------------------------------------------------------------- utilidades
def _paciente(db: Session, paciente_id: str) -> Paciente:
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return p


def nombre_paciente(p: Paciente | None) -> str | None:
    if p is None:
        return None
    try:
        return f"{descifrar(p.nombre_cifrado, 'pacientes.nombre')} {descifrar(p.apellido_cifrado, 'pacientes.apellido')}"
    except Exception:  # noqa: BLE001 -- una clave distinta no tumba el listado
        return None


def vista_reporte(r: dict, p: Paciente | None = None, con_payload: bool = False) -> dict:
    resultado = r.get("resultado") or {}
    salida = {
        "id": r["id"], "paciente_id": r["paciente_id"].strip(),
        "paciente_nombre": nombre_paciente(p),
        "estado": r["estado"],
        "clase": resultado.get("clase"),
        "probabilidad": float(r["probabilidad"]) if r["probabilidad"] is not None else None,
        "critico": r["critico"], "umbral": resultado.get("umbral"),
        "modelo_version": r["modelo_version"],
        "variables_imputadas": resultado.get("variables_imputadas", []),
        "observaciones": r["observaciones"],
        "creado_por": r["creado_por"], "revisado_por": r["revisado_por"],
        "revisado_at": r["revisado_at"], "created_at": r["created_at"],
    }
    if con_payload:
        salida["payload"] = r["payload_enviado"]
    return salida


def _reporte_visible(db: Session, ctx: ContextoAcceso, reporte_id: int) -> tuple[dict, Paciente]:
    """Carga el reporte y aplica el control por registro (NIVEL 2) sobre su paciente."""
    r = db.execute(text("SELECT * FROM reportes_ia WHERE id = :i"), {"i": reporte_id}).mappings().first()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    p = db.get(Paciente, r["paciente_id"])
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    ctx.verificar_registro(p)
    # El paciente solo ve lo que ya entró a su historia clínica.
    if ctx.alcance == "self" and r["estado"] != "aprobado":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    return dict(r), p


def _llamar_modelo(payload: dict) -> dict:
    try:
        resp = httpx.post(f"{settings.ml_url}/predict", json=payload, timeout=settings.ml_timeout_segundos)
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "El servicio de IA no responde. Intente de nuevo en unos segundos.")
    if resp.status_code == 422:
        detalle = resp.json().get("detail") if resp.headers.get("content-type", "").startswith("application/json") else None
        raise HTTPException(422, f"El modelo rechazó los datos: {detalle}")
    if resp.status_code == 503:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El servicio de IA está arriba pero sin modelo cargado.")
    if resp.status_code != 200:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"El servicio de IA respondió {resp.status_code}")
    return resp.json()


def crear_alerta_critica(db: Session, ctx: ContextoAcceso, request: Request,
                         reporte: dict, p: Paciente) -> int:
    """R20: alerta activa para el clínico que pidió el análisis, auditada y empujada por el canal en vivo."""
    resultado = reporte["resultado"] or {}
    prob = float(reporte["probabilidad"])
    a = db.execute(text("""
        INSERT INTO alertas (tipo, severidad, titulo, mensaje, entidad_tipo, entidad_id,
                             dirigida_a_usuario, paciente_id, reporte_id, estado)
        VALUES ('alerta_critica_ia', 'critica', :titulo, :mensaje, 'reporte_ia', :rid,
                :u, :p, :rid, 'activa')
        ON CONFLICT DO NOTHING
        RETURNING *
    """), {
        "titulo": "Riesgo crítico de UCI posoperatoria",
        # Sin datos personales en el texto: el nombre lo pone la vista, solo para quien puede verlo.
        "mensaje": f"El modelo estima {prob:.0%} de riesgo (umbral {resultado.get('umbral', 0):.0%}). "
                   f"Revise y reconozca la alerta.",
        "rid": reporte["id"], "u": ctx.usuario.id, "p": p.documento_bidx,
    }).mappings().first()
    if a is None:
        return db.execute(text("SELECT id FROM alertas WHERE reporte_id = :r"), {"r": reporte["id"]}).scalar()
    registrar(db, ctx.usuario, "alerta", a["id"], "alerta_critica",
              valor_nuevo={"paciente_id": p.documento_bidx, "reporte_id": reporte["id"],
                           "nivel": "critica", "probabilidad": prob}, request=request)
    try:
        reactores.al_alerta_critica(db, _Fila({**dict(a), "tipo": "alerta_critica", "nivel": "critica"}))
    except Exception:  # noqa: BLE001 -- un aviso que falla no tumba el análisis
        pass
    return a["id"]


# ---------------------------------------------------------------- endpoints
@router.post("/analizar", status_code=status.HTTP_201_CREATED, summary="Ejecutar el análisis de IA")
def analizar(datos: Analizar, request: Request,
             ctx: ContextoAcceso = Depends(RequierePermiso("ia", "create")),
             db: Session = Depends(get_db)):
    p = _paciente(db, datos.paciente_id)
    ctx.verificar_registro(p)

    variables = seudo.variables_clinicas(db, p.documento_bidx)
    if not variables:
        raise HTTPException(422,
                            "El paciente no tiene glucosa, potasio ni hemoglobina registradas: "
                            "sin al menos un laboratorio el modelo no puede estimar el riesgo.")
    try:
        payload = seudo.construir_payload(p, variables)
    except seudo.ClaveSeudonimoFaltante:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "La capa de seudonimización no está configurada (IA_SEUDONIMO_KEY).")

    resultado = _llamar_modelo(payload)

    r = db.execute(text("""
        INSERT INTO reportes_ia (paciente_id, creado_por, estado, resultado, probabilidad, critico,
                                 payload_enviado, modelo_version)
        VALUES (:p, :u, 'pendiente', :res, :prob, :crit, :payload, :ver)
        RETURNING *
    """).bindparams(bindparam("res", type_=JSONB), bindparam("payload", type_=JSONB)), {
        "p": p.documento_bidx, "u": ctx.usuario.id, "res": resultado,
        "prob": resultado["probabilidad"], "crit": bool(resultado["critico"]),
        "payload": payload, "ver": resultado.get("modelo_version"),
    }).mappings().first()
    r = dict(r)
    registrar(db, ctx.usuario, "reporte_ia", r["id"], "ia_analisis",
              valor_nuevo={"paciente_id": p.documento_bidx, "estado": "pendiente",
                           "probabilidad": resultado["probabilidad"], "critico": r["critico"],
                           "modelo_version": r["modelo_version"]}, request=request)

    alerta_id = crear_alerta_critica(db, ctx, request, r, p) if r["critico"] else None
    db.commit()
    return {"id": r["id"], "estado": "pendiente", "paciente_id": p.documento_bidx,
            "probabilidad": float(r["probabilidad"]), "critico": r["critico"],
            "clase": resultado.get("clase"), "alerta_id": alerta_id}


@router.get("/reportes", summary="Reportes de IA (por paciente o por estado)")
def listar(paciente_id: str | None = Query(None), estado: str | None = Query(None, pattern="^(pendiente|aprobado|rechazado)$"),
           ctx: ContextoAcceso = Depends(RequierePermiso("ia", "read")),
           db: Session = Depends(get_db)):
    q = select(_reportes.c.id).order_by(_reportes.c.created_at.desc()).limit(200)
    if paciente_id:
        p = _paciente(db, paciente_id)
        ctx.verificar_registro(p)
        q = q.where(_reportes.c.paciente_id == p.documento_bidx)
    if ctx.alcance == "self":
        q = q.where(_reportes.c.paciente_id == ctx.payload.get("paciente_id"), _reportes.c.estado == "aprobado")
    elif ctx.alcance == "assigned":
        q = q.where(_reportes.c.paciente_id.in_(select(ctx.pacientes_asignados_subq())))
    if estado:
        q = q.where(_reportes.c.estado == estado)
    ids = [f[0] for f in db.execute(q)]
    if not ids:
        return {"reportes": []}
    filas = db.execute(text("SELECT * FROM reportes_ia WHERE id = ANY(:ids) ORDER BY created_at DESC"),
                       {"ids": ids}).mappings().all()
    pacientes = {f["paciente_id"]: db.get(Paciente, f["paciente_id"]) for f in filas}
    return {"reportes": [vista_reporte(dict(f), pacientes[f["paciente_id"]]) for f in filas]}


@router.get("/reportes/{reporte_id}", summary="Un reporte de IA")
def obtener(reporte_id: int, ctx: ContextoAcceso = Depends(RequierePermiso("ia", "read")),
            db: Session = Depends(get_db)):
    r, p = _reporte_visible(db, ctx, reporte_id)
    return vista_reporte(r, p)


@router.get("/reportes/{reporte_id}/payload", summary="El JSON exacto que recibió el modelo (R12)")
def payload(reporte_id: int, request: Request,
            ctx: ContextoAcceso = Depends(RequierePermiso("ia", "read")),
            db: Session = Depends(get_db)):
    if ctx.alcance == "self":   # es evidencia técnica para clínicos y auditoría
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El payload del modelo es de uso clínico")
    r, _ = _reporte_visible(db, ctx, reporte_id)
    registrar(db, ctx.usuario, "reporte_ia", reporte_id, "read",
              valor_nuevo={"vista": "payload", "paciente_id": r["paciente_id"]}, request=request)
    db.commit()
    return {"reporte_id": reporte_id, "payload": r["payload_enviado"]}


def _decidir(reporte_id: int, hacia: str, datos: Decision, request: Request,
             ctx: ContextoAcceso, db: Session) -> dict:
    r, p = _reporte_visible(db, ctx, reporte_id)
    if r["estado"] != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, f"El reporte ya está {r['estado']}")
    obs = (datos.observaciones or "").strip() or None
    fila = db.execute(text("""
        UPDATE reportes_ia SET estado = :hacia, observaciones = :obs,
               revisado_por = :u, revisado_at = :t
        WHERE id = :i AND estado = 'pendiente' RETURNING *
    """), {"hacia": hacia, "obs": obs, "u": ctx.usuario.id, "t": datetime.now(timezone.utc),
           "i": reporte_id}).mappings().first()
    if fila is None:   # otro clínico lo decidió entre la lectura y el UPDATE
        raise HTTPException(status.HTTP_409_CONFLICT, "El reporte ya no está pendiente")
    fila = dict(fila)
    registrar(db, ctx.usuario, "reporte_ia", reporte_id, "aprobar" if hacia == "aprobado" else "rechazar",
              valor_anterior={"estado": "pendiente"},
              valor_nuevo={"estado": hacia, "paciente_id": r["paciente_id"], "con_observaciones": obs is not None},
              request=request)
    if hacia == "aprobado":
        try:
            reactores.al_aprobar_reporte(db, _Fila(fila))   # R19: factura automática con reporte_id
        except Exception:  # noqa: BLE001 -- el aviso no tumba la aprobación
            pass
    db.commit()
    return vista_reporte(fila, p)


@router.post("/reportes/{reporte_id}/aprobar", summary="Aprobar: el reporte entra a la historia clínica")
def aprobar(reporte_id: int, request: Request, datos: Decision | None = None,
            ctx: ContextoAcceso = Depends(RequierePermiso("ia", "approve")),
            db: Session = Depends(get_db)):
    return _decidir(reporte_id, "aprobado", datos or Decision(), request, ctx, db)


@router.post("/reportes/{reporte_id}/rechazar", summary="Rechazar: queda como evidencia, no entra a la historia")
def rechazar(reporte_id: int, request: Request, datos: Decision | None = None,
             ctx: ContextoAcceso = Depends(RequierePermiso("ia", "approve")),
             db: Session = Depends(get_db)):
    return _decidir(reporte_id, "rechazado", datos or Decision(), request, ctx, db)
