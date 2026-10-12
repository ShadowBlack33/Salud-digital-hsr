"""
Gestión de usuarios (R01 y R02 del Corte 2).

Solo el admin crea usuarios y desbloquea cuentas: ambas acciones exigen el
permiso 'usuario:manage', que en el catálogo solo tiene el rol admin. No
existe registro público, así que nadie puede asignarse un rol a sí mismo.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.crypto import blind_index
from app.core.deps import ContextoAcceso, RequierePermiso
from app.core.security import hash_password, validar_fortaleza
from app.models import Paciente, Personal, Rol, Usuario
from app.services.auditoria import registrar

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


# ------------------------------------------------------------------ esquemas
class UsuarioCrear(BaseModel):
    username: str = Field(..., min_length=3, max_length=60, pattern=r"^[A-Za-z0-9_.-]+$",
                          examples=["medico02"])
    password: str = Field(..., description="Contraseña inicial. El usuario debe cambiarla al entrar.")
    rol: str = Field(..., examples=["medico"])
    personal_id: int | None = Field(None, description="Para roles asistenciales: su registro en 'personal'.")
    documento_paciente: str | None = Field(
        None, description="Solo para el rol paciente: su número de documento.")


def _vista(u: Usuario) -> dict:
    """Lo que se puede mostrar de una cuenta. Nunca el hash de la contraseña."""
    ahora = datetime.now(timezone.utc)
    bloqueada = bool(u.bloqueado_hasta and u.bloqueado_hasta > ahora)
    return {
        "id": u.id,
        "username": u.username,
        "rol": u.rol.codigo if u.rol else None,
        "rol_nombre": u.rol.nombre if u.rol else None,
        "activo": bool(u.activo),
        "bloqueada": bloqueada,
        "intentos_fallidos": u.intentos_fallidos or 0,
        "ultimo_acceso": u.ultimo_acceso.isoformat() if u.ultimo_acceso else None,
        "personal_id": u.personal_id,
        "tiene_paciente": u.paciente_id is not None,
        "debe_cambiar_password": bool(u.debe_cambiar_password),
    }


# ------------------------------------------------------------------ endpoints
@router.get("", summary="Listar usuarios (solo admin)")
def listar(bloqueadas: bool = Query(False, description="Solo cuentas bloqueadas"),
           ctx: ContextoAcceso = Depends(RequierePermiso("usuario", "manage"))):
    q = ctx.db.query(Usuario).filter(Usuario.activo.is_(True))
    if bloqueadas:
        q = q.filter(Usuario.bloqueado_hasta > datetime.now(timezone.utc))
    return [_vista(u) for u in q.order_by(Usuario.username).all()]


@router.get("/roles", summary="Roles disponibles (solo admin)")
def roles(ctx: ContextoAcceso = Depends(RequierePermiso("usuario", "manage"))):
    filas = ctx.db.query(Rol).filter(Rol.activo.is_(True)).order_by(Rol.nivel_jerarquico, Rol.codigo).all()
    return [{"codigo": r.codigo, "nombre": r.nombre, "es_asistencial": r.es_asistencial} for r in filas]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear usuario (solo admin)")
def crear(datos: UsuarioCrear,
          ctx: ContextoAcceso = Depends(RequierePermiso("usuario", "manage"))):
    db: Session = ctx.db

    rol = db.query(Rol).filter(Rol.codigo == datos.rol, Rol.activo.is_(True)).first()
    if rol is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El rol '{datos.rol}' no existe")

    if db.query(Usuario).filter(Usuario.username == datos.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese nombre de usuario ya existe")

    ok, mensaje = validar_fortaleza(datos.password)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, mensaje)

    paciente_id = None
    if rol.codigo == "paciente":
        if not datos.documento_paciente:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Una cuenta de paciente necesita el documento del paciente")
        paciente_id = blind_index(datos.documento_paciente, "pacientes.documento")
        existe = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                           Paciente.activo.is_(True)).first()
        if existe is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay un paciente activo con ese documento")

    if datos.personal_id is not None:
        if db.get(Personal, datos.personal_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese registro de personal no existe")

    nuevo = Usuario(
        username=datos.username,
        password_hash=hash_password(datos.password),
        rol_id=rol.id,
        personal_id=datos.personal_id,
        paciente_id=paciente_id,
        debe_cambiar_password=True,
        created_by=ctx.usuario.id,
    )
    db.add(nuevo)
    db.flush()
    registrar(db, ctx.usuario, "usuario", nuevo.id, "create",
              valor_nuevo={"username": nuevo.username, "rol": rol.codigo},
              request=ctx.request)
    db.commit()
    db.refresh(nuevo)
    return _vista(nuevo)


@router.post("/{usuario_id}/desbloquear", summary="Desbloquear una cuenta (solo admin)")
def desbloquear(usuario_id: int,
                ctx: ContextoAcceso = Depends(RequierePermiso("usuario", "manage"))):
    db: Session = ctx.db
    u = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.activo.is_(True)).first()
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    antes = {"bloqueado_hasta": u.bloqueado_hasta.isoformat() if u.bloqueado_hasta else None,
             "intentos_fallidos": u.intentos_fallidos or 0}
    u.bloqueado_hasta = None
    u.intentos_fallidos = 0
    registrar(db, ctx.usuario, "usuario", u.id, "desbloqueo",
              valor_anterior=antes,
              valor_nuevo={"bloqueado_hasta": None, "intentos_fallidos": 0, "username": u.username},
              request=ctx.request)
    db.commit()
    db.refresh(u)
    return _vista(u)
