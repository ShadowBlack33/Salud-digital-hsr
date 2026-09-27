"""Modelos SQLAlchemy. Reflejan el esquema de db/01_schema.sql."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer,
    LargeBinary, Numeric, SmallInteger, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ---------------------------------------------------------------- seguridad
class Rol(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(40), unique=True, nullable=False)
    nombre = Column(String(120), nullable=False)
    descripcion = Column(Text)
    es_asistencial = Column(Boolean, default=False)
    es_cuenta_tecnica = Column(Boolean, default=False)
    nivel_jerarquico = Column(SmallInteger, default=5)
    activo = Column(Boolean, default=True)

    permisos = relationship("Permiso", secondary="roles_permisos",
                            back_populates="roles", lazy="selectin")


class Permiso(Base):
    __tablename__ = "permisos"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(80), unique=True, nullable=False)
    recurso = Column(String(40), nullable=False)
    accion = Column(String(30), nullable=False)
    alcance = Column(String(20), default="all")
    descripcion = Column(Text)

    roles = relationship("Rol", secondary="roles_permisos",
                         back_populates="permisos")


class RolPermiso(Base):
    __tablename__ = "roles_permisos"
    rol_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permiso_id = Column(Integer, ForeignKey("permisos.id"), primary_key=True)


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    uuid = Column(UUID(as_uuid=True), server_default=func.gen_random_uuid())
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    rol_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    personal_id = Column(Integer, ForeignKey("personal.id"))
    paciente_id = Column(String(64), ForeignKey("pacientes.documento_bidx"))
    intentos_fallidos = Column(SmallInteger, default=0)
    bloqueado_hasta = Column(DateTime(timezone=True))
    ultimo_acceso = Column(DateTime(timezone=True))
    debe_cambiar_password = Column(Boolean, default=True)
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer)

    rol = relationship("Rol", lazy="joined")

    @property
    def codigos_permisos(self) -> list[str]:
        return [p.codigo for p in self.rol.permisos] if self.rol else []


class Sesion(Base):
    __tablename__ = "sesiones"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    refresh_token_hash = Column(String(64), unique=True, nullable=False)
    ip_origen = Column(String)
    user_agent = Column(Text)
    emitido_at = Column(DateTime(timezone=True), server_default=func.now())
    expira_at = Column(DateTime(timezone=True), nullable=False)
    revocado_at = Column(DateTime(timezone=True))


# ---------------------------------------------------------------- personal
class Especialidad(Base):
    __tablename__ = "especialidades"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(30), unique=True, nullable=False)
    nombre = Column(String(120), nullable=False)
    codigo_snomed = Column(String(20))
    requiere_uci = Column(Boolean, default=False)
    activo = Column(Boolean, default=True)


class Personal(Base):
    __tablename__ = "personal"
    id = Column(Integer, primary_key=True)
    uuid = Column(UUID(as_uuid=True), server_default=func.gen_random_uuid())
    documento_cifrado = Column(LargeBinary, nullable=False)
    documento_bidx = Column(String(64), unique=True, nullable=False)
    nombre_cifrado = Column(LargeBinary, nullable=False)
    apellido_cifrado = Column(LargeBinary, nullable=False)
    telefono_cifrado = Column(LargeBinary)
    email_cifrado = Column(LargeBinary)
    registro_profesional_cifrado = Column(LargeBinary)
    especialidad_id = Column(Integer, ForeignKey("especialidades.id"))
    tipo_personal = Column(String(40), nullable=False)
    tiempo_desplazamiento_min = Column(SmallInteger)
    turno_habitual = Column(String(20))
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer)

    especialidad = relationship("Especialidad", lazy="joined")


# ---------------------------------------------------------------- recursos
class TipoCama(Base):
    __tablename__ = "tipos_cama"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(80), nullable=False)
    nivel_complejidad = Column(SmallInteger, nullable=False)
    codigo_snomed = Column(String(20))
    costo_dia_cop = Column(Numeric(12, 2))
    activo = Column(Boolean, default=True)


class Servicio(Base):
    __tablename__ = "servicios"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(80), nullable=False)
    piso = Column(SmallInteger)
    activo = Column(Boolean, default=True)


class Cama(Base):
    __tablename__ = "camas"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False)
    tipo_cama_id = Column(Integer, ForeignKey("tipos_cama.id"), nullable=False)
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=False)
    estado = Column(String(20), default="disponible")
    estado_desde = Column(DateTime(timezone=True), server_default=func.now())
    fhir_location_id = Column(String(64))
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer)

    tipo_cama = relationship("TipoCama", lazy="joined")
    servicio = relationship("Servicio", lazy="joined")


class Quirofano(Base):
    __tablename__ = "quirofanos"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(80))
    servicio_id = Column(Integer, ForeignKey("servicios.id"))
    tiene_arco_c = Column(Boolean, default=False)
    tiene_circulacion_extracorporea = Column(Boolean, default=False)
    estado = Column(String(20), default="disponible")
    estado_desde = Column(DateTime(timezone=True), server_default=func.now())
    fhir_location_id = Column(String(64))
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer)


# ---------------------------------------------------------------- catálogo
class CatalogoProcedimiento(Base):
    __tablename__ = "catalogo_procedimientos"
    id = Column(Integer, primary_key=True)
    codigo_interno = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(200), nullable=False)
    codigo_snomed = Column(String(20))
    codigo_cups = Column(String(20))
    especialidad_id = Column(Integer, ForeignKey("especialidades.id"), nullable=False)
    duracion_estimada_min = Column(SmallInteger, nullable=False)
    duracion_desviacion_min = Column(SmallInteger, default=20)
    tipo_cama_requerida_id = Column(Integer, ForeignKey("tipos_cama.id"), nullable=False)
    requiere_arco_c = Column(Boolean, default=False)
    complejidad = Column(SmallInteger, default=2)
    tarifa_referencia_cop = Column(Numeric(12, 2))
    activo = Column(Boolean, default=True)

    tipo_cama_requerida = relationship("TipoCama", lazy="joined")
    especialidad = relationship("Especialidad", lazy="joined")


class DiagnosticoCie10(Base):
    __tablename__ = "diagnosticos_cie10"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(10), unique=True, nullable=False)
    descripcion = Column(String(250), nullable=False)
    capitulo = Column(String(120))


class CausaCancelacion(Base):
    __tablename__ = "catalogo_causas_cancelacion"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(30), unique=True, nullable=False)
    descripcion = Column(String(200), nullable=False)
    responsable = Column(String(20), nullable=False)
    origen = Column(String(20))
    evitable = Column(Boolean, default=True)


class Eps(Base):
    __tablename__ = "eps"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(150), nullable=False)
    regimen = Column(String(20))
    activo = Column(Boolean, default=True)


# ---------------------------------------------------------------- clínico
class Paciente(Base):
    __tablename__ = "pacientes"
    # documento_bidx es la llave primaria real (el índice ciego de la cédula),
    # no un id autoincremental -- ver la nota en db/01_schema.sql.
    documento_bidx = Column(String(64), primary_key=True)
    uuid = Column(UUID(as_uuid=True), server_default=func.gen_random_uuid())
    tipo_documento = Column(String(5), nullable=False)
    documento_cifrado = Column(LargeBinary, nullable=False)
    nombre_cifrado = Column(LargeBinary, nullable=False)
    apellido_cifrado = Column(LargeBinary, nullable=False)
    telefono_cifrado = Column(LargeBinary)
    email_cifrado = Column(LargeBinary)
    direccion_cifrada = Column(LargeBinary)
    fecha_nacimiento = Column(Date, nullable=False)
    sexo = Column(String(1), nullable=False)
    eps_id = Column(Integer, ForeignKey("eps.id"))
    tiene_comorbilidades = Column(Boolean, default=False)
    riesgo_asa = Column(SmallInteger)
    consentimiento_datos = Column(Boolean, default=False)
    consentimiento_fecha = Column(DateTime(timezone=True))
    fhir_patient_id = Column(String(64))
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer)
    updated_at = Column(DateTime(timezone=True))

    @property
    def id(self):
        """
        Alias de compatibilidad. El código genérico de auditoría
        (app/services/auditoria.py: soft_delete, soft_edit, restaurar)
        está escrito para cualquier entidad con `.id`, sin saber de cuál
        tabla se trata. Para Paciente esa identidad ya no es un entero
        autoincremental, sino documento_bidx (el índice ciego de la
        cédula) -- ver la nota en db/01_schema.sql.
        Funciona solo a nivel de INSTANCIA (p.id tras un fetch); las
        consultas deben seguir filtrando por Paciente.documento_bidx.
        """
        return self.documento_bidx


class Encuentro(Base):
    __tablename__ = "encuentros"
    id = Column(Integer, primary_key=True)
    uuid = Column(UUID(as_uuid=True), server_default=func.gen_random_uuid())
    paciente_id = Column(String(64), ForeignKey("pacientes.documento_bidx"), nullable=False)
    tipo = Column(String(25), nullable=False)
    estado = Column(String(20), default="planned")
    origen = Column(String(15), default="electiva")
    prioridad_clinica = Column(SmallInteger, default=3)
    nivel_triage = Column(SmallInteger)
    diagnostico_cie10_id = Column(Integer, ForeignKey("diagnosticos_cie10.id"))
    procedimiento_id = Column(Integer, ForeignKey("catalogo_procedimientos.id"))
    quirofano_id = Column(Integer, ForeignKey("quirofanos.id"))
    cama_id = Column(Integer, ForeignKey("camas.id"))
    medico_responsable_id = Column(Integer, ForeignKey("personal.id"))
    anestesiologo_id = Column(Integer, ForeignKey("personal.id"))
    hora_programada_inicio = Column(DateTime(timezone=True))
    hora_programada_fin = Column(DateTime(timezone=True))
    hora_real_inicio = Column(DateTime(timezone=True))
    hora_real_fin = Column(DateTime(timezone=True))
    minutos_desviacion = Column(Integer)
    fhir_encounter_id = Column(String(64))
    observaciones_texto = Column(Text)
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer)
    updated_at = Column(DateTime(timezone=True))

    paciente = relationship("Paciente", lazy="joined")
    procedimiento = relationship("CatalogoProcedimiento", lazy="joined")
    diagnostico = relationship("DiagnosticoCie10", lazy="joined")


class Observacion(Base):
    __tablename__ = "observaciones"
    id = Column(Integer, primary_key=True)
    uuid = Column(UUID(as_uuid=True), server_default=func.gen_random_uuid())
    encuentro_id = Column(Integer, ForeignKey("encuentros.id"), nullable=False)
    paciente_id = Column(String(64), ForeignKey("pacientes.documento_bidx"), nullable=False)
    categoria = Column(String(25), default="vital-signs")
    codigo_loinc = Column(String(20), nullable=False)
    display_loinc = Column(String(150))
    valor_numerico = Column(Numeric(12, 3))
    valor_texto = Column(String(200))
    unidad_ucum = Column(String(20))
    estado = Column(String(20), default="final")
    es_critico = Column(Boolean, default=False)
    fecha_hora = Column(DateTime(timezone=True), server_default=func.now())
    registrado_por = Column(Integer, ForeignKey("personal.id"))
    fhir_observation_id = Column(String(64))
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer)


# ---------------------------------------------------------------- auditoría
class LogAuditoria(Base):
    __tablename__ = "log_auditoria"
    id = Column(BigInteger, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    rol_codigo = Column(String(40))
    entidad_tipo = Column(String(40), nullable=False)
    # String y no Integer a propósito: para 'paciente' aquí va documento_bidx.
    entidad_id = Column(String(64))
    operacion = Column(String(20), nullable=False)
    resultado = Column(String(15), default="exito")
    valor_anterior = Column(JSONB)
    valor_nuevo = Column(JSONB)
    ip_origen = Column(String)
    user_agent = Column(Text)
    endpoint = Column(String(200))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class HistorialCambio(Base):
    __tablename__ = "historial_cambios"
    id = Column(BigInteger, primary_key=True)
    entidad_tipo = Column(String(40), nullable=False)
    # Igual que en LogAuditoria: para 'paciente' aquí va documento_bidx.
    entidad_id = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    campo = Column(String(60), nullable=False)
    valor_anterior = Column(Text)
    valor_nuevo = Column(Text)
    era_cifrado = Column(Boolean, default=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class EventoEstado(Base):
    __tablename__ = "eventos_estado"
    id = Column(BigInteger, primary_key=True)
    entidad_tipo = Column(String(20), nullable=False)
    entidad_id = Column(Integer, nullable=False)
    entidad_subtipo = Column(String(30))
    estado_anterior = Column(String(30))
    estado_nuevo = Column(String(30), nullable=False)
    duracion_estado_anterior_min = Column(Integer)
    motivo = Column(String(200))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    origen = Column(String(20), default="manual")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())