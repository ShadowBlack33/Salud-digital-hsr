"""
Ingeniería biomédica: equipos que sacan de servicio una cama o un quirófano.

  GET  /biomedica/fuera-servicio                 abiertas y cerradas en los últimos 30 días
  POST /biomedica/fuera-servicio                 sacar de servicio (equipo, tipo, descripción)
  POST /biomedica/fuera-servicio/{id}/devolver   devolver a servicio: queda en limpieza

Es lo único que este perfil cambia (permiso equipo:update). No puede mandar a
limpieza, ocupar ni liberar por su cuenta, y nunca ve pacientes. Al devolver,
la cama o el quirófano queda "en limpieza": enfermería lo habilita después.
Res. 4816/2008 (tecnovigilancia) y Res. 3100/2019 (mantenimiento de equipos).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.recursos import _registrar_evento
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Cama, Quirofano
from app.services.auditoria import registrar

router = APIRouter(prefix="/biomedica", tags=["Ingeniería biomédica"])

MODELO = {"cama": Cama, "quirofano": Quirofano}
BLOQUEO = {"cama": "bloqueada", "quirofano": "bloqueado"}
CON_PACIENTE = {"cama": ("ocupada", "reservada", "en_proceso_alta"), "quirofano": ("en_cirugia",)}
TIPOS = {"falla": "Falla", "mantenimiento_preventivo": "Mantenimiento preventivo",
         "mantenimiento_correctivo": "Mantenimiento correctivo"}


class SalidaServicio(BaseModel):
    recurso_tipo: str = Field(..., pattern="^(cama|quirofano)$")
    recurso_id: int
    equipo: str = Field(..., min_length=3, max_length=120)
    tipo: str = Field(..., pattern="^(falla|mantenimiento_preventivo|mantenimiento_correctivo)$")
    descripcion: str = Field(..., min_length=5, max_length=1000)


class Devolucion(BaseModel):
    nota: str | None = Field(None, max_length=1000)


@router.get("/fuera-servicio", summary="Camas y quirófanos fuera de servicio por equipo")
def listar(ctx: ContextoAcceso = Depends(RequierePermiso("equipo", "read")), db: Session = Depends(get_db)):
    filas = db.execute(text("""
        SELECT f.*, COALESCE(c.codigo, q.codigo) AS recurso_codigo,
               COALESCE(tc.nombre, q.nombre) AS recurso_detalle, s.nombre AS servicio,
               tc.costo_dia_cop, u.username AS reportado_por_usuario,
               EXTRACT(EPOCH FROM (COALESCE(f.fin, NOW()) - f.inicio)) / 3600.0 AS horas
        FROM fuera_servicio f
        LEFT JOIN camas c ON f.recurso_tipo = 'cama' AND c.id = f.recurso_id
        LEFT JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        LEFT JOIN servicios s ON s.id = c.servicio_id
        LEFT JOIN quirofanos q ON f.recurso_tipo = 'quirofano' AND q.id = f.recurso_id
        LEFT JOIN usuarios u ON u.id = f.reportado_por
        WHERE f.fin IS NULL OR f.fin > NOW() - INTERVAL '30 days'
        ORDER BY (f.fin IS NULL) DESC, f.inicio DESC
    """)).mappings().all()
    salida = []
    for f in filas:
        d = {k: f[k] for k in ("id", "recurso_tipo", "recurso_id", "recurso_codigo", "recurso_detalle", "servicio",
                               "equipo", "tipo", "descripcion", "inicio", "fin", "nota_cierre",
                               "reportado_por_usuario")}
        d["tipo_texto"] = TIPOS.get(f["tipo"], f["tipo"])
        d["abierta"] = f["fin"] is None
        d["horas"] = round(float(f["horas"] or 0), 1)
        # Costo de oportunidad aproximado: solo camas (costo día del tipo de cama).
        d["costo_estimado_cop"] = round(d["horas"] * float(f["costo_dia_cop"]) / 24) if f["costo_dia_cop"] else None
        salida.append(d)
    return {"fuera_servicio": salida, "abiertas": sum(1 for d in salida if d["abierta"])}


@router.post("/fuera-servicio", status_code=status.HTTP_201_CREATED, summary="Sacar de servicio por equipo")
def sacar(datos: SalidaServicio, request: Request,
          ctx: ContextoAcceso = Depends(RequierePermiso("equipo", "update")), db: Session = Depends(get_db)):
    modelo = MODELO[datos.recurso_tipo]
    obj = db.query(modelo).filter(modelo.id == datos.recurso_id, modelo.activo.is_(True)) \
        .with_for_update(of=modelo).first()
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa cama o quirófano")
    if obj.estado in CON_PACIENTE[datos.recurso_tipo]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{obj.codigo} tiene un paciente ({obj.estado}). Coordina primero el traslado con "
                            "enfermería; luego sácalo de servicio.")
    if db.execute(text("SELECT 1 FROM fuera_servicio WHERE recurso_tipo = :t AND recurso_id = :i AND fin IS NULL"),
                  {"t": datos.recurso_tipo, "i": obj.id}).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{obj.codigo} ya está fuera de servicio")
    anterior = obj.estado
    motivo = f"{TIPOS[datos.tipo]} · {datos.equipo.strip()}"
    _registrar_evento(db, datos.recurso_tipo, obj, BLOQUEO[datos.recurso_tipo], ctx.usuario, motivo[:200])
    fila = db.execute(text("""
        INSERT INTO fuera_servicio (recurso_tipo, recurso_id, equipo, tipo, descripcion, estado_anterior, reportado_por)
        VALUES (:rt, :ri, :eq, :ti, :de, :ea, :u) RETURNING id
    """), {"rt": datos.recurso_tipo, "ri": obj.id, "eq": datos.equipo.strip(), "ti": datos.tipo,
           "de": datos.descripcion.strip(), "ea": anterior, "u": ctx.usuario.id}).first()
    registrar(db, ctx.usuario, datos.recurso_tipo, obj.id, "update", valor_anterior={"estado": anterior},
              valor_nuevo={"estado": obj.estado, "fuera_servicio_id": fila[0], "equipo": datos.equipo,
                           "tipo": datos.tipo}, request=request)
    db.commit()
    return {"id": fila[0], "recurso": obj.codigo, "estado": obj.estado}


@router.post("/fuera-servicio/{salida_id}/devolver", summary="Devolver a servicio (queda en limpieza)")
def devolver(salida_id: int, request: Request, datos: Devolucion | None = None,
             ctx: ContextoAcceso = Depends(RequierePermiso("equipo", "update")), db: Session = Depends(get_db)):
    f = db.execute(text("SELECT * FROM fuera_servicio WHERE id = :i FOR UPDATE"), {"i": salida_id}).mappings().first()
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese registro")
    if f["fin"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya fue devuelto a servicio")
    modelo = MODELO[f["recurso_tipo"]]
    obj = db.query(modelo).filter(modelo.id == f["recurso_id"]).with_for_update(of=modelo).first()
    anterior = obj.estado
    if anterior == BLOQUEO[f["recurso_tipo"]]:
        _registrar_evento(db, f["recurso_tipo"], obj, "en_limpieza", ctx.usuario,
                          f"Equipo reparado: {f['equipo']}"[:200])
    nota = (datos.nota.strip() if datos and datos.nota else None)
    db.execute(text("UPDATE fuera_servicio SET fin = :t, cerrado_por = :u, nota_cierre = :n WHERE id = :i"),
               {"t": datetime.now(timezone.utc), "u": ctx.usuario.id, "n": nota, "i": salida_id})
    registrar(db, ctx.usuario, f["recurso_tipo"], obj.id, "update", valor_anterior={"estado": anterior},
              valor_nuevo={"estado": obj.estado, "fuera_servicio_id": salida_id}, request=request)
    db.commit()
    return {"id": salida_id, "recurso": obj.codigo, "estado": obj.estado}
