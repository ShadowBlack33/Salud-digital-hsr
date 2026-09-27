"""
Autenticación y autorización.

  · Contraseñas: Argon2id (ganador del Password Hashing Competition).
    NO bcrypt, NO SHA. Argon2id resiste ataques con GPU y con hardware
    dedicado gracias a su coste en memoria.

  · Tokens: JWT de vida corta (15 min) + refresh token rotativo (7 días).
    El refresh se guarda hasheado en BD para poder revocarlo de verdad;
    un JWT por sí solo no se puede revocar antes de que expire.

  · Autorización: RBAC granular con permisos en base de datos.
    Dos niveles obligatorios:
       nivel 1  -> ¿el rol tiene el permiso?          (endpoint)
       nivel 2  -> ¿sobre ESE registro en concreto?   (fila)
    Comprobar solo el nivel 1 dejaría a un médico editar los pacientes
    de otro médico.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext

from dotenv import load_dotenv
load_dotenv()

# --------------------------------------------------------------------------
# Contraseñas
# --------------------------------------------------------------------------

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__memory_cost=65536,   # 64 MiB
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verificar_password(password: str, hash_almacenado: str) -> bool:
    return pwd_context.verify(password, hash_almacenado)


def validar_fortaleza(password: str) -> tuple[bool, str]:
    """Política mínima de contraseñas para un sistema con datos de salud."""
    if len(password) < 12:
        return False, "La contraseña debe tener al menos 12 caracteres"
    if not any(c.isupper() for c in password):
        return False, "Debe incluir al menos una mayúscula"
    if not any(c.islower() for c in password):
        return False, "Debe incluir al menos una minúscula"
    if not any(c.isdigit() for c in password):
        return False, "Debe incluir al menos un número"
    if not any(not c.isalnum() for c in password):
        return False, "Debe incluir al menos un carácter especial"
    return True, "OK"


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

ALGORITMO = "HS256"
ACCESS_TOKEN_MINUTOS = 15
REFRESH_TOKEN_DIAS = 7


def _secreto_jwt() -> str:
    s = os.getenv("JWT_SECRET_KEY")
    if not s:
        raise RuntimeError("Falta JWT_SECRET_KEY en el entorno")
    return s


def crear_access_token(usuario_id: int, username: str, rol_codigo: str,
                       permisos: list[str], personal_id: int | None = None,
                       paciente_id: int | None = None) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "username": username,
        "rol": rol_codigo,
        "permisos": permisos,
        "personal_id": personal_id,
        "paciente_id": paciente_id,
        "type": "access",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=ACCESS_TOKEN_MINUTOS),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, _secreto_jwt(), algorithm=ALGORITMO)


def crear_refresh_token() -> tuple[str, str, datetime]:
    """
    Devuelve (token_claro, hash_para_bd, fecha_expiracion).
    En BD se guarda solo el hash: si alguien lee la tabla no puede
    suplantar sesiones.
    """
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expira = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DIAS)
    return token, token_hash, expira


def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secreto_jwt(), algorithms=[ALGORITMO])
    except JWTError as e:
        raise ValueError(f"Token inválido: {e}")


# --------------------------------------------------------------------------
# Autorización RBAC
# --------------------------------------------------------------------------

class Alcance(str, Enum):
    ALL = "all"           # cualquier registro
    OWN = "own"           # solo los que él creó
    ASSIGNED = "assigned" # solo los que le asignaron
    SELF = "self"         # solo su propia información (paciente)


class ErrorAutorizacion(Exception):
    def __init__(self, mensaje: str, codigo: int = 403):
        self.mensaje = mensaje
        self.codigo = codigo
        super().__init__(mensaje)


def tiene_permiso(permisos_usuario: list[str], recurso: str, accion: str) -> str | None:
    """
    Nivel 1: ¿el rol puede ejecutar esta acción sobre este tipo de recurso?
    Devuelve el alcance más amplio concedido, o None si no tiene permiso.

    Orden de prioridad: all > assigned > own > self
    """
    for alcance in ("all", "assigned", "own", "self"):
        if f"{recurso}:{accion}:{alcance}" in permisos_usuario:
            return alcance
    # permisos sin alcance explícito (ej. 'paciente:restore')
    if f"{recurso}:{accion}" in permisos_usuario:
        return "all"
    return None


def verificar_acceso_registro(alcance: str, registro, token_payload: dict,
                              recurso: str) -> bool:
    """
    Nivel 2: dado el alcance concedido, ¿puede tocar ESTE registro?

    registro debe exponer:  created_by  y, para 'self', paciente_id.
    """
    if alcance == Alcance.ALL:
        return True

    usuario_id = int(token_payload["sub"])

    if alcance == Alcance.OWN:
        creador = getattr(registro, "created_by", None)
        if creador != usuario_id:
            raise ErrorAutorizacion(
                f"Solo puede operar sobre los registros de {recurso} que usted creó"
            )
        return True

    if alcance == Alcance.SELF:
        paciente_token = token_payload.get("paciente_id")
        paciente_registro = getattr(registro, "paciente_id", None) or getattr(registro, "id", None)
        if paciente_token is None or paciente_token != paciente_registro:
            raise ErrorAutorizacion("Solo puede consultar su propia información")
        return True

    if alcance == Alcance.ASSIGNED:
        personal_token = token_payload.get("personal_id")
        asignados = [
            getattr(registro, "medico_responsable_id", None),
            getattr(registro, "anestesiologo_id", None),
            getattr(registro, "registrado_por", None),
        ]
        if personal_token is None or personal_token not in asignados:
            raise ErrorAutorizacion(
                f"Solo puede acceder a los registros de {recurso} que tiene asignados"
            )
        return True

    raise ErrorAutorizacion("Alcance de permiso desconocido")


if __name__ == "__main__":
    os.environ.setdefault("JWT_SECRET_KEY", secrets.token_urlsafe(32))

    h = hash_password("Quirofano#2026Seg")
    assert verificar_password("Quirofano#2026Seg", h)
    assert not verificar_password("otra", h)
    assert h.startswith("$argon2id$")

    ok, msg = validar_fortaleza("corta")
    assert not ok
    ok, _ = validar_fortaleza("Quirofano#2026Seg")
    assert ok

    t = crear_access_token(1, "jmesa", "medico_especialista",
                           ["paciente:read:all", "paciente:update:own"], personal_id=5)
    d = decodificar_token(t)
    assert d["rol"] == "medico_especialista"

    assert tiene_permiso(d["permisos"], "paciente", "read") == "all"
    assert tiene_permiso(d["permisos"], "paciente", "update") == "own"
    assert tiene_permiso(d["permisos"], "paciente", "delete") is None

    class Fake:
        created_by = 99
    try:
        verificar_acceso_registro("own", Fake(), d, "paciente")
        raise AssertionError("debió denegar")
    except ErrorAutorizacion:
        pass

    print("security.py: todas las pruebas pasaron")
    print("  hash argon2:", h[:40], "...")
