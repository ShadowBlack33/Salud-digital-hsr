"""Dependencias compartidas: sesión de BD, usuario actual y guardas de permisos."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import (
    ErrorAutorizacion, decodificar_token, tiene_permiso,
    verificar_acceso_registro,
)
from app.models import Usuario

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.debug,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

bearer = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_token_payload(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if cred is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Se requiere autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decodificar_token(cred.credentials)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Se requiere un token de acceso")
    return payload


def get_usuario_actual(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> Usuario:
    usuario = db.query(Usuario).filter(
        Usuario.id == int(payload["sub"]),
        Usuario.activo.is_(True),
    ).first()
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Usuario inexistente o desactivado")
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_423_LOCKED,
                            "Cuenta bloqueada temporalmente")
    return usuario


class RequierePermiso:
    """
    Guarda de NIVEL 1: ¿el rol puede ejecutar esta acción sobre este recurso?

    Uso:
        @router.delete("/pacientes/{id}")
        def borrar(ctx = Depends(RequierePermiso("paciente", "delete"))):
            ...

    Devuelve un contexto con el alcance concedido, que el endpoint
    debe usar después con `verificar_registro` (NIVEL 2).
    """

    def __init__(self, recurso: str, accion: str):
        self.recurso = recurso
        self.accion = accion

    def __call__(
        self,
        request: Request,
        payload: dict = Depends(get_token_payload),
        usuario: Usuario = Depends(get_usuario_actual),
        db: Session = Depends(get_db),
    ) -> "ContextoAcceso":
        permisos = payload.get("permisos", [])
        alcance = tiene_permiso(permisos, self.recurso, self.accion)

        if alcance is None:
            from app.services.auditoria import registrar
            registrar(db, usuario, self.recurso, None, self.accion,
                      resultado="denegado", request=request)
            db.commit()
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"El rol '{payload.get('rol')}' no tiene permiso para "
                f"{self.accion} sobre {self.recurso}",
            )

        return ContextoAcceso(
            usuario=usuario, payload=payload, alcance=alcance,
            recurso=self.recurso, accion=self.accion, db=db, request=request,
        )


class ContextoAcceso:
    """Contexto de una petición autorizada."""

    def __init__(self, usuario, payload, alcance, recurso, accion, db, request):
        self.usuario = usuario
        self.payload = payload
        self.alcance = alcance
        self.recurso = recurso
        self.accion = accion
        self.db = db
        self.request = request

    # ---------------------------------------------------- pacientes asignados
    # Un médico o especialista solo trabaja con SUS pacientes (alcance
    # 'assigned' en paciente:read). Son suyos los que él registró y los que
    # tienen un encuentro a su cargo (médico responsable o anestesiólogo).
    # Las remisiones aceptadas se suman en `pacientes_asignados_subq` cuando
    # exista la tabla del módulo de remisiones.
    def alcance_paciente(self) -> str | None:
        return tiene_permiso(self.payload.get("permisos", []), "paciente", "read")

    def pacientes_asignados_subq(self):
        """Subconsulta con los documento_bidx de los pacientes de este usuario."""
        from sqlalchemy import or_, select, text, union
        from app.models import Encuentro, Paciente
        personal_id = self.payload.get("personal_id")
        partes = [select(Paciente.documento_bidx).where(Paciente.created_by == self.usuario.id)]
        if personal_id is not None:
            partes.append(select(Encuentro.paciente_id).where(
                Encuentro.activo.is_(True),
                or_(Encuentro.medico_responsable_id == personal_id,
                    Encuentro.anestesiologo_id == personal_id)))
            if _hay_tabla_remisiones(self.db):
                partes.append(select(text("paciente_id")).select_from(text("remisiones")).where(
                    text("especialista_id = :pid AND estado IN ('aceptada','atendida')")
                    .bindparams(pid=personal_id)))
        return union(*partes).subquery()

    def es_paciente_asignado(self, paciente_id: str) -> bool:
        from sqlalchemy import exists, select
        sub = self.pacientes_asignados_subq()
        return bool(self.db.scalar(select(exists().where(sub.c[0] == paciente_id))))

    def verificar_registro(self, registro) -> None:
        """
        Guarda de NIVEL 2: ¿puede tocar ESTE registro en concreto?
        Sin esta llamada, un médico podría editar los pacientes de otro.
        """
        from app.models import Paciente
        if isinstance(registro, Paciente) and self.alcance_paciente() == "assigned":
            # Vale para cualquier recurso que cuelgue del paciente (imágenes,
            # historia, IA): si no es su paciente, no ve nada de él.
            if not self.es_paciente_asignado(registro.documento_bidx):
                from app.services.auditoria import registrar
                registrar(self.db, self.usuario, self.recurso, None, self.accion,
                          resultado="denegado", request=self.request)
                self.db.commit()
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                                    "Este paciente no está a su cargo")
            if self.alcance in ("all", "assigned"):
                return
        try:
            verificar_acceso_registro(self.alcance, registro,
                                      self.payload, self.recurso)
        except ErrorAutorizacion as e:
            from app.services.auditoria import registrar
            registrar(self.db, self.usuario, self.recurso,
                      getattr(registro, "id", None), self.accion,
                      resultado="denegado", request=self.request)
            self.db.commit()
            raise HTTPException(e.codigo, e.mensaje)

    def filtrar_query(self, query, modelo):
        """Aplica el filtro de alcance a una consulta de listado."""
        if self.alcance == "own":
            return query.filter(modelo.created_by == self.usuario.id)
        if self.alcance == "self":
            pid = self.payload.get("paciente_id")
            if hasattr(modelo, "paciente_id"):
                campo = modelo.paciente_id
            else:
                # Paciente se referencia a sí mismo: no tiene columna
                # paciente_id, su llave real es documento_bidx. (modelo.id
                # a nivel de CLASE no sirve aquí: es un property de Python,
                # no una columna consultable -- solo funciona en instancias.)
                campo = modelo.documento_bidx
            return query.filter(campo == pid)
        if self.alcance == "assigned":
            personal_id = self.payload.get("personal_id")
            if hasattr(modelo, "medico_responsable_id"):
                from sqlalchemy import or_
                return query.filter(or_(modelo.medico_responsable_id == personal_id,
                                        modelo.anestesiologo_id == personal_id))
            from app.models import Paciente
            if modelo is Paciente:
                sub = self.pacientes_asignados_subq()
                return query.filter(Paciente.documento_bidx.in_(sub.select()))
        return query


_REMISIONES: dict[str, bool] = {}


def _hay_tabla_remisiones(db) -> bool:
    """¿Ya existe la tabla del módulo de remisiones? Se consulta una sola vez."""
    if "ok" not in _REMISIONES:
        from sqlalchemy import text
        try:
            _REMISIONES["ok"] = db.execute(text("SELECT to_regclass('public.remisiones') IS NOT NULL")).scalar() \
                and db.execute(text("""SELECT COUNT(*) = 3 FROM information_schema.columns
                                       WHERE table_name = 'remisiones'
                                         AND column_name IN ('paciente_id','especialista_id','estado')""")).scalar()
        except Exception:  # noqa: BLE001
            _REMISIONES["ok"] = False
    return bool(_REMISIONES["ok"])
