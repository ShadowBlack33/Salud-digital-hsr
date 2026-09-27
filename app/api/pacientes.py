"""
Pacientes: CRUD con cifrado transparente y operaciones soft.

Este módulo es la referencia del patrón que siguen las demás entidades:
  · NIVEL 1 de autorización -> RequierePermiso(...) en la firma
  · NIVEL 2 de autorización -> ctx.verificar_registro(obj)
  · Todo GET filtra activo == True (si no, el soft delete no se notaría)
  · Los identificadores viajan cifrados hacia la BD y se descifran al leer
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.crypto import blind_index, cifrar, descifrar, enmascarar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Paciente
from app.services.auditoria import registrar, restaurar, snapshot, soft_delete, soft_edit

router = APIRouter(prefix="/pacientes", tags=["Pacientes"])


# ------------------------------------------------------------------ esquemas
class PacienteCrear(BaseModel):
    tipo_documento: str = Field(..., max_length=5, examples=["CC"])
    documento: str = Field(..., examples=["1144098765"])
    nombre: str
    apellido: str
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None
    fecha_nacimiento: date
    sexo: str = Field(..., pattern="^[MFO]$")
    eps_id: int | None = None
    tiene_comorbilidades: bool = False
    riesgo_asa: int | None = Field(None, ge=1, le=5)
    consentimiento_datos: bool = False


class PacienteActualizar(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None
    eps_id: int | None = None
    tiene_comorbilidades: bool | None = None
    riesgo_asa: int | None = Field(None, ge=1, le=5)
    consentimiento_datos: bool | None = None


class PacienteRespuesta(BaseModel):
    # La llave ya no es un entero autoincremental: es documento_bidx, el
    # índice ciego (HMAC-SHA256) de la cédula del paciente. Es la misma
    # llave que se usa en encuentros.paciente_id, observaciones.paciente_id,
    # etc. No es reversible: no se puede recuperar la cédula a partir de ella.
    paciente_id: str
    tipo_documento: str
    documento: str
    nombre: str
    apellido: str
    telefono: str | None = None
    fecha_nacimiento: date
    sexo: str
    eps_id: int | None = None
    tiene_comorbilidades: bool
    riesgo_asa: int | None = None
    activo: bool
    fhir_patient_id: str | None = None
    created_by: int | None = None


def _a_respuesta(p: Paciente, enmascarar_doc: bool = False) -> PacienteRespuesta:
    doc = descifrar(p.documento_cifrado, "pacientes.documento")
    tel = descifrar(p.telefono_cifrado, "pacientes.telefono") if p.telefono_cifrado else None
    return PacienteRespuesta(
        paciente_id=p.documento_bidx,
        tipo_documento=p.tipo_documento,
        documento=enmascarar(doc) if enmascarar_doc else doc,
        nombre=descifrar(p.nombre_cifrado, "pacientes.nombre"),
        apellido=descifrar(p.apellido_cifrado, "pacientes.apellido"),
        telefono=tel,
        fecha_nacimiento=p.fecha_nacimiento,
        sexo=p.sexo,
        eps_id=p.eps_id,
        tiene_comorbilidades=bool(p.tiene_comorbilidades),
        riesgo_asa=p.riesgo_asa,
        activo=bool(p.activo),
        fhir_patient_id=p.fhir_patient_id,
        created_by=p.created_by,
    )


# ------------------------------------------------------------------ endpoints
@router.post("", response_model=PacienteRespuesta,
             status_code=status.HTTP_201_CREATED,
             summary="Registrar paciente")
def crear(datos: PacienteCrear, request: Request,
          ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "create")),
          db: Session = Depends(get_db)):
    bidx = blind_index(datos.documento, "pacientes.documento")
    if db.query(Paciente).filter(Paciente.documento_bidx == bidx).first():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ya existe un paciente con ese documento")

    p = Paciente(
        tipo_documento=datos.tipo_documento,
        documento_cifrado=cifrar(datos.documento, "pacientes.documento"),
        documento_bidx=bidx,
        nombre_cifrado=cifrar(datos.nombre, "pacientes.nombre"),
        apellido_cifrado=cifrar(datos.apellido, "pacientes.apellido"),
        telefono_cifrado=cifrar(datos.telefono, "pacientes.telefono"),
        email_cifrado=cifrar(datos.email, "pacientes.email"),
        direccion_cifrada=cifrar(datos.direccion, "pacientes.direccion"),
        fecha_nacimiento=datos.fecha_nacimiento,
        sexo=datos.sexo,
        eps_id=datos.eps_id,
        tiene_comorbilidades=datos.tiene_comorbilidades,
        riesgo_asa=datos.riesgo_asa,
        consentimiento_datos=datos.consentimiento_datos,
        consentimiento_fecha=datetime.now(timezone.utc) if datos.consentimiento_datos else None,
        created_by=ctx.usuario.id,
    )
    db.add(p)
    db.flush()
    registrar(db, ctx.usuario, "paciente", p.id, "create",
              valor_nuevo=snapshot(p), request=request)
    db.commit()
    db.refresh(p)
    return _a_respuesta(p)


@router.get("", response_model=list[PacienteRespuesta],
            summary="Listar pacientes activos")
def listar(ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
           db: Session = Depends(get_db),
           limite: int = Query(50, le=200), offset: int = Query(0, ge=0),
           incluir_eliminados: bool = Query(False)):
    q = db.query(Paciente)
    # CLAVE: sin este filtro los registros "borrados" seguirían apareciendo
    if not incluir_eliminados:
        q = q.filter(Paciente.activo.is_(True))
    elif ctx.alcance != "all":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Solo un rol con alcance total puede ver eliminados")

    q = ctx.filtrar_query(q, Paciente)
    pacientes = q.order_by(Paciente.documento_bidx).offset(offset).limit(limite).all()
    # En listados el documento va enmascarado (minimización de exposición)
    return [_a_respuesta(p, enmascarar_doc=True) for p in pacientes]


@router.get("/buscar", response_model=PacienteRespuesta,
            summary="Buscar por documento (usa blind index)")
def buscar(documento: str,
           ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
           db: Session = Depends(get_db)):
    """
    Busca sin descifrar toda la tabla: compara el HMAC determinístico
    del documento contra la columna documento_bidx.
    """
    bidx = blind_index(documento, "pacientes.documento")
    p = db.query(Paciente).filter(Paciente.documento_bidx == bidx,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    ctx.verificar_registro(p)
    return _a_respuesta(p)


@router.get("/{paciente_id}", response_model=PacienteRespuesta,
            summary="Consultar paciente")
def obtener(paciente_id: str, request: Request,
            ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
            db: Session = Depends(get_db)):
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    ctx.verificar_registro(p)          # NIVEL 2
    registrar(db, ctx.usuario, "paciente", p.id, "read", request=request)
    db.commit()
    return _a_respuesta(p)


@router.put("/{paciente_id}", response_model=PacienteRespuesta,
            summary="Editar paciente (soft edit con historial)")
def actualizar(paciente_id: str, datos: PacienteActualizar, request: Request,
               ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "update")),
               db: Session = Depends(get_db)):
    """
    Soft edit: el valor anterior de cada campo modificado se conserva
    en historial_cambios en vez de sobrescribirse.
    """
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    ctx.verificar_registro(p)

    cambios: dict = {}
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is None:
            continue
        if campo in ("nombre", "apellido", "telefono", "email", "direccion"):
            col = "direccion_cifrada" if campo == "direccion" else f"{campo}_cifrado"
            cambios[col] = cifrar(valor, f"pacientes.{campo}")
        else:
            cambios[campo] = valor

    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se enviaron cambios")

    soft_edit(db, p, cambios, ctx.usuario, "paciente", request=request)
    db.commit()
    db.refresh(p)
    return _a_respuesta(p)


@router.delete("/{paciente_id}", summary="Eliminar paciente (soft delete)")
def eliminar(paciente_id: str, request: Request,
             ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "delete")),
             db: Session = Depends(get_db)):
    """
    Marca como inactivo sin borrar físicamente.
    admin -> cualquier paciente | clínico -> solo los que él registró.
    """
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Paciente no encontrado o ya eliminado")
    ctx.verificar_registro(p)
    soft_delete(db, p, ctx.usuario, "paciente", request=request)
    db.commit()
    return {"mensaje": f"Paciente {paciente_id} marcado como inactivo",
            "restaurable_por": "admin"}


@router.post("/{paciente_id}/restaurar", response_model=PacienteRespuesta,
             summary="Restaurar paciente eliminado (SOLO admin)")
def restaurar_paciente(paciente_id: str, request: Request,
                       ctx: ContextoAcceso = Depends(
                           RequierePermiso("paciente", "restore")),
                       db: Session = Depends(get_db)):
    """
    Undelete. Reservado exclusivamente al rol admin, incluso cuando
    el registro fue eliminado por un médico.
    """
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    if p.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "El paciente no está eliminado")
    restaurar(db, p, ctx.usuario, "paciente", request=request)
    db.commit()
    db.refresh(p)
    return _a_respuesta(p)


@router.get("/{paciente_id}/historial", summary="Historial de cambios")
def historial(paciente_id: str,
              ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
              db: Session = Depends(get_db)):
    from app.models import HistorialCambio
    filas = (db.query(HistorialCambio)
             .filter(HistorialCambio.entidad_tipo == "paciente",
                     HistorialCambio.entidad_id == paciente_id)
             .order_by(HistorialCambio.version.desc(),
                       HistorialCambio.timestamp.desc()).all())
    return [{
        "version": h.version, "campo": h.campo,
        "valor_anterior": h.valor_anterior, "valor_nuevo": h.valor_nuevo,
        "era_cifrado": h.era_cifrado, "usuario_id": h.usuario_id,
        "timestamp": h.timestamp,
    } for h in filas]
