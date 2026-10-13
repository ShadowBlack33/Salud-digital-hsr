"""Autenticación: login, refresh, logout y cambio de contraseña."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_db, get_token_payload, get_usuario_actual
from app.core.security import (
    crear_access_token, crear_refresh_token, hash_password,
    validar_fortaleza, verificar_password,
)
from app.models import Sesion, Usuario
from app.services import reactores
from app.services.auditoria import registrar

router = APIRouter(prefix="/auth", tags=["Autenticación"])
settings = get_settings()
log = logging.getLogger("hsr.auth")

# Bloqueo "hasta que el admin lo quite": una fecha que nunca llega.
BLOQUEO_INDEFINIDO = datetime(9999, 1, 1, tzinfo=timezone.utc)


def _respuesta_bloqueo(usuario: Usuario) -> JSONResponse:
    """423 uniforme para toda cuenta bloqueada."""
    requiere_admin = usuario.bloqueado_hasta >= BLOQUEO_INDEFINIDO
    contenido = {
        "detail": ("Cuenta bloqueada por intentos fallidos. Pida al administrador que la desbloquee."
                   if requiere_admin else
                   f"Cuenta bloqueada hasta {usuario.bloqueado_hasta.isoformat()}"),
        "requiere_admin": requiere_admin,
        "intentos_restantes": 0,
        "max_intentos": settings.max_intentos_login,
    }
    if not requiere_admin:
        contenido["bloqueado_hasta"] = usuario.bloqueado_hasta.isoformat()
    return JSONResponse(status_code=status.HTTP_423_LOCKED, content=contenido)


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
        # R13: el intento sobre una cuenta bloqueada también queda trazado,
        # aunque traiga la contraseña correcta (R02 exige rechazarlo).
        registrar(db, usuario, "usuario", usuario.id, "login",
                  resultado="denegado", request=request)
        db.commit()
        return _respuesta_bloqueo(usuario)

    if not usuario.activo:
        raise generico

    if not verificar_password(datos.password, usuario.password_hash):
        usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
        bloqueada_ahora = usuario.intentos_fallidos >= settings.max_intentos_login
        if bloqueada_ahora:
            # R02: con bloqueo_requiere_admin la cuenta queda bloqueada hasta
            # que el admin la libere (POST /usuarios/{id}/desbloquear). Se
            # guarda como una fecha muy lejana para no cambiar el esquema: el
            # resto del sistema ya trata "bloqueado_hasta > ahora" como bloqueo.
            usuario.bloqueado_hasta = (BLOQUEO_INDEFINIDO if settings.bloqueo_requiere_admin
                                       else ahora + timedelta(minutes=settings.minutos_bloqueo))
            usuario.intentos_fallidos = 0
        restantes = (0 if bloqueada_ahora
                     else settings.max_intentos_login - usuario.intentos_fallidos)
        registrar(db, usuario, "usuario", usuario.id, "login",
                  resultado="denegado", request=request)
        if bloqueada_ahora:
            registrar(db, usuario, "usuario", usuario.id, "bloqueo",
                      valor_nuevo={"username": usuario.username,
                                   "intentos": settings.max_intentos_login,
                                   "requiere_admin": settings.bloqueo_requiere_admin},
                      request=request)
            try:
                reactores.al_bloquear(db, usuario)   # R19: aviso al admin
            except Exception:  # un aviso fallido no puede deshacer el bloqueo
                log.exception("No se pudo avisar del bloqueo de %s", usuario.username)
        db.commit()

        if bloqueada_ahora:
            # El intento que agota el contador ya responde 423: el usuario se
            # entera de inmediato. Se responde así aunque login_mostrar_intentos
            # esté apagado, porque R02 exige que el bloqueo sea explícito.
            return _respuesta_bloqueo(usuario)
        if not settings.login_mostrar_intentos:
            raise generico
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={
            "detail": "Credenciales inválidas",
            "intentos_restantes": restantes,
            "max_intentos": settings.max_intentos_login,
        })

    usuario.intentos_fallidos = 0
    usuario.ultimo_acceso = ahora

    permisos = usuario.codigos_permisos
    refresh, refresh_hash, expira = crear_refresh_token()
    sesion = Sesion(
        usuario_id=usuario.id,
        refresh_token_hash=refresh_hash,
        ip_origen=None,
        user_agent=request.headers.get("user-agent"),
        expira_at=expira,
    )
    db.add(sesion)
    db.flush()   # id de la sesión para ligarlo al token
    access = crear_access_token(
        usuario.id, usuario.username, usuario.rol.codigo, permisos,
        usuario.personal_id, usuario.paciente_id, sesion.id,
    )
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
    # Una cuenta bloqueada no puede seguir renovando la sesión que ya tenía.
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.now(timezone.utc):
        return _respuesta_bloqueo(usuario)

    sesion.revocado_at = datetime.now(timezone.utc)

    permisos = usuario.codigos_permisos
    nuevo_refresh, nuevo_hash, expira = crear_refresh_token()
    nueva = Sesion(usuario_id=usuario.id, refresh_token_hash=nuevo_hash, expira_at=expira)
    db.add(nueva)
    db.flush()
    access = crear_access_token(usuario.id, usuario.username, usuario.rol.codigo,
                                permisos, usuario.personal_id, usuario.paciente_id, nueva.id)
    db.commit()

    return TokenResponse(
        access_token=access, refresh_token=nuevo_refresh,
        expira_en_segundos=15 * 60, rol=usuario.rol.codigo, permisos=permisos,
        debe_cambiar_password=bool(usuario.debe_cambiar_password),
    )


@router.post("/logout", summary="Cerrar sesión")
def logout(datos: RefreshRequest, request: Request, db: Session = Depends(get_db),
           usuario: Usuario = Depends(get_usuario_actual),
           payload: dict = Depends(get_token_payload)):
    """Revoca la sesión: el refresh y también el access token ligado (sid)."""
    token_hash = hashlib.sha256(datos.refresh_token.encode()).hexdigest()
    ahora = datetime.now(timezone.utc)
    db.query(Sesion).filter(
        Sesion.usuario_id == usuario.id, Sesion.revocado_at.is_(None),
        (Sesion.refresh_token_hash == token_hash) | (Sesion.id == payload.get("sid", -1)),
    ).update({"revocado_at": ahora}, synchronize_session=False)
    registrar(db, usuario, "usuario", usuario.id, "logout", request=request)
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
        # El front lo usa para obligar a cambiar la contraseña inicial.
        "debe_cambiar_password": bool(usuario.debe_cambiar_password),
    }
