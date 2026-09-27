"""Autenticación: login, refresh, logout y cambio de contraseña."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_db, get_usuario_actual
from app.core.security import (
    crear_access_token, crear_refresh_token, hash_password,
    validar_fortaleza, verificar_password,
)
from app.models import Sesion, Usuario
from app.services.auditoria import registrar

router = APIRouter(prefix="/auth", tags=["Autenticación"])
settings = get_settings()


class LoginRequest(BaseModel):
    username: str = Field(..., examples=["admin"])
    password: str = Field(..., examples=["Demo#Hospital2026"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expira_en_segundos: int
    rol: str
    permisos: list[str]
    debe_cambiar_password: bool


class RefreshRequest(BaseModel):
    refresh_token: str


class CambioPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión")
def login(datos: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Autentica y devuelve un par de tokens.

    Protecciones:
      · Respuesta genérica ante usuario inexistente o contraseña incorrecta
        (no revela cuál de los dos falló).
      · Bloqueo temporal tras varios intentos fallidos.
    """
    usuario = db.query(Usuario).filter(Usuario.username == datos.username).first()
    generico = HTTPException(status.HTTP_401_UNAUTHORIZED,
                             "Credenciales inválidas")

    if usuario is None:
        # Se hashea igualmente para no filtrar por tiempo de respuesta
        hash_password(datos.password)
        raise generico

    ahora = datetime.now(timezone.utc)
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Cuenta bloqueada hasta {usuario.bloqueado_hasta.isoformat()}",
        )

    if not usuario.activo:
        raise generico

    if not verificar_password(datos.password, usuario.password_hash):
        usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
        if usuario.intentos_fallidos >= settings.max_intentos_login:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=settings.minutos_bloqueo)
            usuario.intentos_fallidos = 0
        registrar(db, usuario, "usuario", usuario.id, "login",
                  resultado="denegado", request=request)
        db.commit()
        raise generico

    usuario.intentos_fallidos = 0
    usuario.ultimo_acceso = ahora

    permisos = usuario.codigos_permisos
    access = crear_access_token(
        usuario.id, usuario.username, usuario.rol.codigo, permisos,
        usuario.personal_id, usuario.paciente_id,
    )
    refresh, refresh_hash, expira = crear_refresh_token()

    db.add(Sesion(
        usuario_id=usuario.id,
        refresh_token_hash=refresh_hash,
        ip_origen=None,
        user_agent=request.headers.get("user-agent"),
        expira_at=expira,
    ))
    registrar(db, usuario, "usuario", usuario.id, "login", request=request)
    db.commit()

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expira_en_segundos=15 * 60,
        rol=usuario.rol.codigo,
        permisos=permisos,
        debe_cambiar_password=bool(usuario.debe_cambiar_password),
    )


@router.post("/refresh", response_model=TokenResponse, summary="Renovar token")
def refresh_token(datos: RefreshRequest, request: Request,
                  db: Session = Depends(get_db)):
    """Rota el refresh token: el anterior se revoca al usarlo."""
    token_hash = hashlib.sha256(datos.refresh_token.encode()).hexdigest()
    sesion = db.query(Sesion).filter(
        Sesion.refresh_token_hash == token_hash,
        Sesion.revocado_at.is_(None),
    ).first()

    if sesion is None or sesion.expira_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Refresh token inválido o expirado")

    usuario = db.query(Usuario).filter(Usuario.id == sesion.usuario_id,
                                       Usuario.activo.is_(True)).first()
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no válido")

    sesion.revocado_at = datetime.now(timezone.utc)

    permisos = usuario.codigos_permisos
    access = crear_access_token(usuario.id, usuario.username, usuario.rol.codigo,
                                permisos, usuario.personal_id, usuario.paciente_id)
    nuevo_refresh, nuevo_hash, expira = crear_refresh_token()
    db.add(Sesion(usuario_id=usuario.id, refresh_token_hash=nuevo_hash,
                  expira_at=expira))
    db.commit()

    return TokenResponse(
        access_token=access, refresh_token=nuevo_refresh,
        expira_en_segundos=15 * 60, rol=usuario.rol.codigo, permisos=permisos,
        debe_cambiar_password=bool(usuario.debe_cambiar_password),
    )


@router.post("/logout", summary="Cerrar sesión")
def logout(datos: RefreshRequest, db: Session = Depends(get_db),
           usuario: Usuario = Depends(get_usuario_actual)):
    token_hash = hashlib.sha256(datos.refresh_token.encode()).hexdigest()
    sesion = db.query(Sesion).filter(
        Sesion.refresh_token_hash == token_hash,
        Sesion.usuario_id == usuario.id,
    ).first()
    if sesion:
        sesion.revocado_at = datetime.now(timezone.utc)
        db.commit()
    return {"mensaje": "Sesión cerrada"}


@router.post("/cambiar-password", summary="Cambiar contraseña")
def cambiar_password(datos: CambioPasswordRequest, request: Request,
                     db: Session = Depends(get_db),
                     usuario: Usuario = Depends(get_usuario_actual)):
    if not verificar_password(datos.password_actual, usuario.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "La contraseña actual no es correcta")

    ok, mensaje = validar_fortaleza(datos.password_nueva)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, mensaje)

    usuario.password_hash = hash_password(datos.password_nueva)
    usuario.password_actualizado_at = datetime.now(timezone.utc)
    usuario.debe_cambiar_password = False

    # Revocar todas las sesiones: obliga a reautenticarse en todos los dispositivos
    db.query(Sesion).filter(Sesion.usuario_id == usuario.id,
                            Sesion.revocado_at.is_(None)) \
        .update({"revocado_at": datetime.now(timezone.utc)})

    registrar(db, usuario, "usuario", usuario.id, "update", request=request)
    db.commit()
    return {"mensaje": "Contraseña actualizada. Vuelva a iniciar sesión."}


@router.get("/yo", summary="Información de la sesión actual")
def yo(usuario: Usuario = Depends(get_usuario_actual)):
    return {
        "id": usuario.id,
        "username": usuario.username,
        "rol": usuario.rol.codigo,
        "rol_nombre": usuario.rol.nombre,
        "es_asistencial": usuario.rol.es_asistencial,
        "permisos": usuario.codigos_permisos,
        "personal_id": usuario.personal_id,
        "paciente_id": usuario.paciente_id,
    }
