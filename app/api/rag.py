"""
POST /rag/preguntar · Asistente con recuperación aumentada (Semana 12).

  · Control de rol: usa el permiso ia:read (db/historial/13_ia.sql). Médicos y
    especialistas (sus pacientes) y admin (todos). El paciente (alcance
    'self') y los roles sin ia:read (contable, coordinador...) reciben 403,
    auditado.
  · Filtro clínico antes de rankear (ver app/services/rag.py).
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

from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Paciente
from app.services import rag as svc
from app.services.auditoria import registrar

router = APIRouter(prefix="/rag", tags=["RAG"])


class Pregunta(BaseModel):
    pregunta: str = Field(..., min_length=5, max_length=500,
                          examples=["¿Desde qué cifra de potasio la hiperpotasemia es grave?"])
    paciente_id: str | None = Field(None, description="Limita la historia a un paciente (debe ser suyo)")
    metodo: Literal["hibrido", "bm25", "denso"] = "hibrido"


@router.post("/preguntar", summary="Preguntar a las guías y a la historia aprobada, con citas")
def preguntar(datos: Pregunta, request: Request,
              ctx: ContextoAcceso = Depends(RequierePermiso("ia", "read")),   # nivel 1
              db: Session = Depends(get_db)):
    if ctx.alcance == "self":
        registrar(db, ctx.usuario, "rag_consulta", None, "rag_preguntar", resultado="denegado", request=request)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El asistente es solo para el equipo clínico")

    if datos.paciente_id:                                                   # nivel 2
        p = db.query(Paciente).filter(Paciente.documento_bidx == datos.paciente_id,
                                      Paciente.activo.is_(True)).first()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
        ctx.verificar_registro(p)

    hallazgo = svc.buscar(db, ctx, datos.pregunta, datos.paciente_id, datos.metodo)
    frags = hallazgo["fragmentos"]
    resp = svc.responder(datos.pregunta, frags)

    citas = []
    for n in resp["citas_usadas"]:
        f = frags[n - 1]
        citas.append({
            "id": f"F{n}", "fragmento_id": f["id"], "documento_id": f["documento_id"], "tipo": f["tipo"],
            "titulo": f["titulo"], "seccion": f["seccion"], "fuente": f["fuente"],
            "paciente": svc.seudonimo(f["paciente_id"]) if f["paciente_id"] else None,
            "extracto": f["texto"][:300],
        })

    rol = getattr(getattr(ctx.usuario, "rol", None), "codigo", None)
    consulta_id = db.execute(text("""
        INSERT INTO rag_consultas (usuario_id, rol, pregunta, paciente_id, metodo, fuentes, abstencion,
                                   confianza, generador)
        VALUES (:u, :rol, :q, :pid, :m, CAST(:f AS jsonb), :a, :c, :g) RETURNING id
    """), {"u": ctx.usuario.id, "rol": rol, "q": datos.pregunta, "pid": datos.paciente_id,
           "m": hallazgo["metodo_usado"], "f": json.dumps([c["fragmento_id"] for c in citas]),
           "a": resp["abstencion"], "c": hallazgo["confianza"], "g": resp["generador"]}).scalar()
    registrar(db, ctx.usuario, "rag_consulta", consulta_id, "rag_preguntar", request=request)
    db.commit()

    return {"consulta_id": consulta_id, "respuesta": resp["respuesta"], "abstencion": resp["abstencion"],
            "citas": citas, "confianza": hallazgo["confianza"], "metodo": hallazgo["metodo_usado"],
            "generador": resp["generador"]}
