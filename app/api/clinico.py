"""Encuentros clínicos y observaciones. Mismo patrón de autorización que pacientes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import CatalogoProcedimiento, Cama, Encuentro, Observacion
from app.services.auditoria import registrar, restaurar, snapshot, soft_delete, soft_edit

router = APIRouter(tags=["Clínico"])


# ============================================================== ENCUENTROS
class EncuentroCrear(BaseModel):
    paciente_id: str
    tipo: str = Field(..., pattern="^(urgencias|cirugia|hospitalizacion|consulta_externa)$")
    origen: str = Field("electiva", pattern="^(electiva|urgencia)$")
    prioridad_clinica: int = Field(3, ge=1, le=5)
    nivel_triage: int | None = Field(None, ge=1, le=5)
    procedimiento_id: int | None = None
    diagnostico_cie10_id: int | None = None
    quirofano_id: int | None = None
    cama_id: int | None = None
    medico_responsable_id: int | None = None
    anestesiologo_id: int | None = None
    hora_programada_inicio: datetime | None = None
    hora_programada_fin: datetime | None = None


class EncuentroActualizar(BaseModel):
    estado: str | None = Field(None, pattern="^(planned|arrived|triaged|in-progress|onleave|finished|cancelled)$")
    prioridad_clinica: int | None = Field(None, ge=1, le=5)
    quirofano_id: int | None = None
    cama_id: int | None = None
    hora_real_inicio: datetime | None = None
    hora_real_fin: datetime | None = None
    observaciones_texto: str | None = None


class EncuentroRespuesta(BaseModel):
    id: int
    paciente_id: str
    tipo: str
    estado: str
    origen: str
    prioridad_clinica: int
    procedimiento_id: int | None = None
    quirofano_id: int | None = None
    cama_id: int | None = None
    medico_responsable_id: int | None = None
    hora_programada_inicio: datetime | None = None
    hora_programada_fin: datetime | None = None
    hora_real_inicio: datetime | None = None
    hora_real_fin: datetime | None = None
    minutos_desviacion: int | None = None
    activo: bool
    created_by: int | None = None

    class Config:
        from_attributes = True


@router.post("/encuentros", response_model=EncuentroRespuesta,
             status_code=status.HTTP_201_CREATED, summary="Crear encuentro")
def crear_encuentro(datos: EncuentroCrear, request: Request,
                    ctx: ContextoAcceso = Depends(RequierePermiso("encuentro", "create")),
                    db: Session = Depends(get_db)):
    """
    Valida la compatibilidad procedimiento <-> tipo de cama.

    Regla de negocio derivada del trabajo de campo: el tipo de cama de
    recuperación depende del procedimiento (una cirugía cardiovascular
    requiere UCI, no una cama general).
    """
    if datos.procedimiento_id and datos.cama_id:
        proc = db.query(CatalogoProcedimiento).get(datos.procedimiento_id)
        cama = db.query(Cama).get(datos.cama_id)
        if proc and cama and cama.tipo_cama_id != proc.tipo_cama_requerida_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"El procedimiento '{proc.nombre}' requiere una cama de tipo "
                f"'{proc.tipo_cama_requerida.codigo}', pero la cama {cama.codigo} "
                f"es de tipo '{cama.tipo_cama.codigo}'",
            )

    e = Encuentro(**datos.model_dump(), created_by=ctx.usuario.id)
    db.add(e)
    db.flush()
    registrar(db, ctx.usuario, "encuentro", e.id, "create",
              valor_nuevo=snapshot(e), request=request)
    db.commit()
    db.refresh(e)
    return e


@router.get("/encuentros", response_model=list[EncuentroRespuesta],
            summary="Listar encuentros")
def listar_encuentros(ctx: ContextoAcceso = Depends(RequierePermiso("encuentro", "read")),
                      db: Session = Depends(get_db),
                      tipo: str | None = None, estado: str | None = None,
                      limite: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    q = db.query(Encuentro).filter(Encuentro.activo.is_(True))
    if tipo:
        q = q.filter(Encuentro.tipo == tipo)
    if estado:
        q = q.filter(Encuentro.estado == estado)
    q = ctx.filtrar_query(q, Encuentro)
    return q.order_by(Encuentro.id.desc()).offset(offset).limit(limite).all()


@router.get("/encuentros/{encuentro_id}", response_model=EncuentroRespuesta,
            summary="Consultar encuentro")
def obtener_encuentro(encuentro_id: int,
                      ctx: ContextoAcceso = Depends(RequierePermiso("encuentro", "read")),
                      db: Session = Depends(get_db)):
    e = db.query(Encuentro).filter(Encuentro.id == encuentro_id,
                                   Encuentro.activo.is_(True)).first()
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")
    ctx.verificar_registro(e)
    return e


@router.put("/encuentros/{encuentro_id}", response_model=EncuentroRespuesta,
            summary="Editar encuentro (soft edit)")
def actualizar_encuentro(encuentro_id: int, datos: EncuentroActualizar, request: Request,
                         ctx: ContextoAcceso = Depends(RequierePermiso("encuentro", "update")),
                         db: Session = Depends(get_db)):
    e = db.query(Encuentro).filter(Encuentro.id == encuentro_id,
                                   Encuentro.activo.is_(True)).first()
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")
    ctx.verificar_registro(e)

    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se enviaron cambios")
    soft_edit(db, e, cambios, ctx.usuario, "encuentro", request=request)
    db.commit()
    db.refresh(e)
    return e


@router.delete("/encuentros/{encuentro_id}", summary="Eliminar encuentro (soft delete)")
def eliminar_encuentro(encuentro_id: int, request: Request,
                       ctx: ContextoAcceso = Depends(RequierePermiso("encuentro", "delete")),
                       db: Session = Depends(get_db)):
    e = db.query(Encuentro).filter(Encuentro.id == encuentro_id,
                                   Encuentro.activo.is_(True)).first()
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")
    ctx.verificar_registro(e)
    soft_delete(db, e, ctx.usuario, "encuentro", request=request)
    db.commit()
    return {"mensaje": f"Encuentro {encuentro_id} marcado como inactivo",
            "restaurable_por": "admin"}


@router.post("/encuentros/{encuentro_id}/restaurar", response_model=EncuentroRespuesta,
             summary="Restaurar encuentro (SOLO admin)")
def restaurar_encuentro(encuentro_id: int, request: Request,
                        ctx: ContextoAcceso = Depends(RequierePermiso("encuentro", "restore")),
                        db: Session = Depends(get_db)):
    e = db.query(Encuentro).get(encuentro_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")
    if e.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El encuentro no está eliminado")
    restaurar(db, e, ctx.usuario, "encuentro", request=request)
    db.commit()
    db.refresh(e)
    return e


# ============================================================ OBSERVACIONES
class ObservacionCrear(BaseModel):
    encuentro_id: int
    paciente_id: str
    categoria: str = Field("vital-signs", pattern="^(vital-signs|laboratory|imaging|survey)$")
    codigo_loinc: str = Field(..., examples=["8867-4"])
    display_loinc: str | None = Field(None, examples=["Heart rate"])
    valor_numerico: float | None = None
    valor_texto: str | None = None
    unidad_ucum: str | None = Field(None, examples=["/min"])
    es_critico: bool = False
    registrado_por: int | None = None


class ObservacionActualizar(BaseModel):
    valor_numerico: float | None = None
    valor_texto: str | None = None
    estado: str | None = Field(None, pattern="^(registered|preliminary|final|amended|cancelled)$")
    es_critico: bool | None = None


class ObservacionRespuesta(BaseModel):
    id: int
    encuentro_id: int
    paciente_id: str
    categoria: str
    codigo_loinc: str
    display_loinc: str | None = None
    valor_numerico: float | None = None
    valor_texto: str | None = None
    unidad_ucum: str | None = None
    estado: str
    es_critico: bool
    fecha_hora: datetime | None = None
    activo: bool
    created_by: int | None = None

    class Config:
        from_attributes = True


@router.post("/observaciones", response_model=ObservacionRespuesta,
             status_code=status.HTTP_201_CREATED, summary="Registrar observación")
def crear_observacion(datos: ObservacionCrear, request: Request,
                      ctx: ContextoAcceso = Depends(RequierePermiso("observacion", "create")),
                      db: Session = Depends(get_db)):
    o = Observacion(**datos.model_dump(), created_by=ctx.usuario.id)
    db.add(o)
    db.flush()
    registrar(db, ctx.usuario, "observacion", o.id, "create",
              valor_nuevo=snapshot(o), request=request)
    db.commit()
    db.refresh(o)
    return o


@router.get("/observaciones", response_model=list[ObservacionRespuesta],
            summary="Listar observaciones")
def listar_observaciones(ctx: ContextoAcceso = Depends(RequierePermiso("observacion", "read")),
                         db: Session = Depends(get_db),
                         encuentro_id: int | None = None,
                         solo_criticas: bool = False,
                         limite: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    q = db.query(Observacion).filter(Observacion.activo.is_(True))
    if encuentro_id:
        q = q.filter(Observacion.encuentro_id == encuentro_id)
    if solo_criticas:
        q = q.filter(Observacion.es_critico.is_(True))
    q = ctx.filtrar_query(q, Observacion)
    return q.order_by(Observacion.id.desc()).offset(offset).limit(limite).all()


@router.put("/observaciones/{observacion_id}", response_model=ObservacionRespuesta,
            summary="Editar observación (soft edit)")
def actualizar_observacion(observacion_id: int, datos: ObservacionActualizar, request: Request,
                           ctx: ContextoAcceso = Depends(RequierePermiso("observacion", "update")),
                           db: Session = Depends(get_db)):
    o = db.query(Observacion).filter(Observacion.id == observacion_id,
                                     Observacion.activo.is_(True)).first()
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observación no encontrada")
    ctx.verificar_registro(o)
    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se enviaron cambios")
    soft_edit(db, o, cambios, ctx.usuario, "observacion", request=request)
    db.commit()
    db.refresh(o)
    return o


@router.delete("/observaciones/{observacion_id}", summary="Eliminar observación (soft delete)")
def eliminar_observacion(observacion_id: int, request: Request,
                         ctx: ContextoAcceso = Depends(RequierePermiso("observacion", "delete")),
                         db: Session = Depends(get_db)):
    o = db.query(Observacion).filter(Observacion.id == observacion_id,
                                     Observacion.activo.is_(True)).first()
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observación no encontrada")
    ctx.verificar_registro(o)
    soft_delete(db, o, ctx.usuario, "observacion", request=request)
    db.commit()
    return {"mensaje": f"Observación {observacion_id} marcada como inactiva",
            "restaurable_por": "admin"}


@router.post("/observaciones/{observacion_id}/restaurar", response_model=ObservacionRespuesta,
             summary="Restaurar observación (SOLO admin)")
def restaurar_observacion(observacion_id: int, request: Request,
                          ctx: ContextoAcceso = Depends(RequierePermiso("observacion", "restore")),
                          db: Session = Depends(get_db)):
    o = db.query(Observacion).get(observacion_id)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observación no encontrada")
    if o.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La observación no está eliminada")
    restaurar(db, o, ctx.usuario, "observacion", request=request)
    db.commit()
    db.refresh(o)
    return o
