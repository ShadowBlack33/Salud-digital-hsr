"""
POST /rag/preguntar · Asistente con recuperación aumentada (Semana 12).

  · Lo usan todos los perfiles, pero cada uno solo recupera lo que le
    corresponde (filtro en SQL antes de rankear, app/services/rag.py):
      - guías: según la audiencia de cada una (clínicas para el personal
        asistencial, el protocolo de Pulso también para el coordinador, la de
        facturación para el contable);
      - historias aprobadas: según el permiso ia:read que ya existe (médico y
        especialista sus pacientes, admin todos, paciente la suya, el resto
        ninguna).
  · Citas: cada respuesta trae los fragmentos que la sustentan.
  · Abstención: sin evidencia suficiente no se llama al modelo.
  · Auditoría: cada consulta queda en rag_consultas y en el log de auditoría.
"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import ContextoAcceso, get_db, get_token_payload, get_usuario_actual
from app.core.security import tiene_permiso
from app.models import Paciente
from app.services import asistente_sistema
from app.services import rag as svc
from app.services.auditoria import registrar

router = APIRouter(prefix="/rag", tags=["RAG"])


class Pregunta(BaseModel):
    pregunta: str = Field(..., min_length=5, max_length=500,
                          examples=["¿Desde qué cifra de potasio la hiperpotasemia es grave?"])
    paciente_id: str | None = Field(None, description="Limita la historia a un paciente (debe ser suyo)")
    metodo: Literal["hibrido", "bm25", "denso"] = "hibrido"


def contexto_rag(request: Request, payload: dict = Depends(get_token_payload),
                 usuario=Depends(get_usuario_actual), db: Session = Depends(get_db)) -> ContextoAcceso:
    """Cualquier usuario autenticado. El alcance sobre historias es el de ia:read (o None)."""
    return ContextoAcceso(usuario=usuario, payload=payload,
                          alcance=tiene_permiso(payload.get("permisos", []), "ia", "read"),
                          recurso="ia", accion="read", db=db, request=request)


def _denegar(db: Session, ctx: ContextoAcceso, request: Request, mensaje: str):
    registrar(db, ctx.usuario, "rag_consulta", None, "rag_preguntar", resultado="denegado", request=request)
    db.commit()
    raise HTTPException(status.HTTP_403_FORBIDDEN, mensaje)


def fuentes_del_perfil(db: Session, ctx: ContextoAcceso) -> list[str]:
    """Qué puede consultar este perfil (para orientar cuando el asistente se abstiene)."""
    guias = db.execute(text("""
        SELECT titulo FROM (SELECT DISTINCT documento_id, titulo FROM rag_fragmentos
                            WHERE tipo = 'guia' AND :rol = ANY(audiencia)) g ORDER BY documento_id
    """), {"rol": ctx.payload.get("rol") or ""}).scalars().all()
    historias = {"all": "La historia aprobada de todos los pacientes",
                 "assigned": "La historia aprobada de tus pacientes (reportes de IA aprobados y encuentros)",
                 "self": "Tu propia historia aprobada"}.get(ctx.alcance)
    return list(guias) + ([historias] if historias else [])


@router.get("/fuentes", summary="Qué fuentes puede consultar mi perfil en el asistente")
def fuentes(ctx: ContextoAcceso = Depends(contexto_rag), db: Session = Depends(get_db)):
    return {"fuentes": fuentes_del_perfil(db, ctx)}


@router.post("/preguntar", summary="Preguntar a las guías y a la historia aprobada, con citas")
def preguntar(datos: Pregunta, request: Request,
              ctx: ContextoAcceso = Depends(contexto_rag),
              db: Session = Depends(get_db)):
    if datos.paciente_id:                       # preguntar por un paciente concreto
        if ctx.alcance is None:
            _denegar(db, ctx, request, "Su perfil no consulta historias clínicas")
        if ctx.alcance == "self":
            if datos.paciente_id != ctx.payload.get("paciente_id"):
                _denegar(db, ctx, request, "Solo puede preguntar por su propia historia")
        else:
            p = db.query(Paciente).filter(Paciente.documento_bidx == datos.paciente_id,
                                          Paciente.activo.is_(True)).first()
            if p is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
            ctx.verificar_registro(p)

    # Preguntas sobre la operación ("¿cuántos pacientes tengo?", "¿qué te puedo
    # preguntar?"): se responden con datos en vivo y los permisos del perfil, sin
    # pasar por Grok (app/services/asistente_sistema.py). El resto va al RAG.
    if not datos.paciente_id:
        sistema = asistente_sistema.responder(db, ctx, datos.pregunta)
        if sistema is not None:
            cita = {"id": "S1", "fragmento_id": None, "documento_id": f"SISTEMA:{sistema['intencion']}",
                    "tipo": "sistema", "titulo": "Datos en vivo de Pulso", "seccion": sistema["intencion"],
                    "fuente": asistente_sistema.FUENTE, "paciente": None, "extracto": None}
            consulta_id = db.execute(text("""
                INSERT INTO rag_consultas (usuario_id, rol, pregunta, paciente_id, metodo, fuentes, abstencion,
                                           confianza, generador, parametros)
                VALUES (:u, :rol, :q, NULL, 'sistema', CAST(:f AS jsonb), :a, NULL, 'sistema', '{}'::jsonb) RETURNING id
            """), {"u": ctx.usuario.id, "rol": ctx.payload.get("rol"), "q": datos.pregunta,
                   "f": json.dumps([cita["documento_id"]]), "a": not sistema["permitida"]}).scalar()
            registrar(db, ctx.usuario, "rag_consulta", consulta_id, "rag_preguntar",
                      resultado="exito" if sistema["permitida"] else "denegado", request=request)
            db.commit()
            return {"consulta_id": consulta_id, "respuesta": sistema["respuesta"],
                    "abstencion": not sistema["permitida"], "citas": [cita] if sistema["permitida"] else [],
                    "confianza": None, "metodo": "sistema", "generador": "sistema"}

    hallazgo = svc.buscar(db, ctx, datos.pregunta, datos.paciente_id, datos.metodo)
    frags = hallazgo["fragmentos"]
    rol = ctx.payload.get("rol")
    resp = svc.responder(datos.pregunta, frags, rol, estricto=hallazgo.get("estricto", True))

    citas = []
    for n in resp["citas_usadas"]:
        f = frags[n - 1]
        citas.append({
            "id": f"F{n}", "fragmento_id": f["id"], "documento_id": f["documento_id"], "tipo": f["tipo"],
            "titulo": f["titulo"], "seccion": f["seccion"], "fuente": f["fuente"],
            "paciente": svc.seudonimo(f["paciente_id"]) if f["paciente_id"] else None,
            "extracto": f["texto"][:300],
        })

    # parametros: con qué modelo, temperatura, versión del prompt, embeddings y reranker se
    # respondió, para poder reproducir (y auditar) una respuesta después.
    consulta_id = db.execute(text("""
        INSERT INTO rag_consultas (usuario_id, rol, pregunta, paciente_id, metodo, fuentes, abstencion,
                                   confianza, generador, parametros)
        VALUES (:u, :rol, :q, :pid, :m, CAST(:f AS jsonb), :a, :c, :g, CAST(:par AS jsonb)) RETURNING id
    """), {"u": ctx.usuario.id, "rol": rol, "q": datos.pregunta, "pid": datos.paciente_id,
           "m": hallazgo["metodo_usado"], "f": json.dumps([c["fragmento_id"] for c in citas]),
           "a": resp["abstencion"], "c": hallazgo["confianza"], "g": resp["generador"],
           "par": json.dumps(svc.parametros(resp["generador"], hallazgo.get("reranker", False),
                                            hallazgo.get("firma")))}).scalar()
    registrar(db, ctx.usuario, "rag_consulta", consulta_id, "rag_preguntar", request=request)
    db.commit()

    salida = {"consulta_id": consulta_id, "respuesta": resp["respuesta"], "abstencion": resp["abstencion"],
              "citas": citas, "confianza": hallazgo["confianza"], "metodo": hallazgo["metodo_usado"],
              "generador": resp["generador"]}
    if resp["abstencion"]:
        # Sin evidencia no se inventa nada, pero se dice qué sí se puede preguntar.
        salida["fuentes_disponibles"] = fuentes_del_perfil(db, ctx)
    return salida
