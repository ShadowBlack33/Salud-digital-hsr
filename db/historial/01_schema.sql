-- ============================================================================
-- SISTEMA DE COORDINACIÓN DE CAPACIDAD QUIRÚRGICA
-- Hospital San Rafael (caso hipotético, ~300 camas, ~13 quirófanos)
--
-- Esquema completo diseñado para TODO el semestre:
--   Semana 6  -> BD + FHIR + roles + soft ops
--   Adelante  -> app móvil, IA de predicción, agentes, dashboard
--
-- Motor: PostgreSQL 14+
-- Cifrado: a nivel de aplicación (AES-256-GCM). La BD almacena BYTEA.
--          Ver docs/SEGURIDAD.md para la justificación.
-- ============================================================================

-- Extensiones -----------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS "citext";     -- texto case-insensitive (emails)

-- ============================================================================
-- SECCIÓN 1 : SEGURIDAD, ROLES Y PERMISOS (RBAC granular)
-- ============================================================================

-- Roles del sistema. Modelo RBAC con permisos en tabla, NO hardcodeados,
-- para poder añadir roles sin tocar código.
CREATE TABLE roles (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(40)  NOT NULL UNIQUE,   -- 'medico_especialista'
    nombre              VARCHAR(120) NOT NULL,
    descripcion         TEXT,
    es_asistencial      BOOLEAN NOT NULL DEFAULT FALSE, -- ¿toca pacientes?
    es_cuenta_tecnica   BOOLEAN NOT NULL DEFAULT FALSE, -- ¿cuenta de máquina?
    nivel_jerarquico    SMALLINT NOT NULL DEFAULT 5,    -- 1 = mayor autoridad
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE roles IS 'Roles del sistema. Ver 02_seed_catalogos.sql para el catálogo poblado.';

-- Permisos atómicos. Formato: recurso:accion[:alcance]
--   ej. 'paciente:read:all', 'paciente:read:own', 'registro:restore'
CREATE TABLE permisos (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(80) NOT NULL UNIQUE,
    recurso         VARCHAR(40) NOT NULL,   -- paciente, encuentro, observacion...
    accion          VARCHAR(30) NOT NULL,   -- create, read, update, delete, restore
    alcance         VARCHAR(20) NOT NULL DEFAULT 'all', -- all | own | assigned
    descripcion     TEXT
);

CREATE TABLE roles_permisos (
    rol_id      INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permiso_id  INT NOT NULL REFERENCES permisos(id) ON DELETE CASCADE,
    PRIMARY KEY (rol_id, permiso_id)
);

-- ============================================================================
-- SECCIÓN 2 : PERSONAL Y USUARIOS
-- ============================================================================

CREATE TABLE especialidades (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(30) NOT NULL UNIQUE,
    nombre          VARCHAR(120) NOT NULL,
    codigo_snomed   VARCHAR(20),            -- VERIFICAR en browser.ihtsdotools.org
    requiere_uci    BOOLEAN NOT NULL DEFAULT FALSE, -- sus cirugías suelen ir a UCI
    activo          BOOLEAN NOT NULL DEFAULT TRUE
);

-- Personal del hospital. Datos identificatorios CIFRADOS (BYTEA).
-- NOTA DE PRIVACIDAD: NO se almacena dirección de residencia (Ley 1581/2012).
-- Solo el tiempo de desplazamiento estimado, que es el dato con valor predictivo.
CREATE TABLE personal (
    id                          SERIAL PRIMARY KEY,
    uuid                        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    documento_cifrado           BYTEA NOT NULL,          -- AES-256-GCM
    documento_bidx              CHAR(64) NOT NULL UNIQUE,-- blind index HMAC-SHA256
    nombre_cifrado              BYTEA NOT NULL,
    apellido_cifrado            BYTEA NOT NULL,
    telefono_cifrado            BYTEA,
    email_cifrado               BYTEA,
    registro_profesional_cifrado BYTEA,                  -- tarjeta profesional
    especialidad_id             INT REFERENCES especialidades(id),
    tipo_personal               VARCHAR(40) NOT NULL,    -- medico_especialista, enfermero_jefe...
    tiempo_desplazamiento_min   SMALLINT,                -- variable predictiva (NO dirección)
    turno_habitual              VARCHAR(20),             -- manana, tarde, noche, rotativo
    activo                      BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at                  TIMESTAMPTZ,
    deleted_by                  INT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by                  INT,
    updated_at                  TIMESTAMPTZ
);
CREATE INDEX idx_personal_especialidad ON personal(especialidad_id) WHERE activo;
CREATE INDEX idx_personal_tipo         ON personal(tipo_personal)   WHERE activo;

-- Cuentas de acceso al sistema.
CREATE TABLE usuarios (
    id                      SERIAL PRIMARY KEY,
    uuid                    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    username                CITEXT NOT NULL UNIQUE,
    password_hash           TEXT NOT NULL,              -- Argon2id
    rol_id                  INT NOT NULL REFERENCES roles(id),
    personal_id             INT REFERENCES personal(id),-- NULL en cuentas técnicas
    paciente_id             CHAR(64),                   -- FK diferida (rol paciente) -- = pacientes.documento_bidx
    mfa_habilitado          BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_secret_cifrado      BYTEA,
    intentos_fallidos       SMALLINT NOT NULL DEFAULT 0,
    bloqueado_hasta         TIMESTAMPTZ,
    ultimo_acceso           TIMESTAMPTZ,
    password_actualizado_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    debe_cambiar_password   BOOLEAN NOT NULL DEFAULT TRUE,
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at              TIMESTAMPTZ,
    deleted_by              INT REFERENCES usuarios(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              INT REFERENCES usuarios(id)
);
CREATE INDEX idx_usuarios_rol ON usuarios(rol_id) WHERE activo;

-- Sesiones / refresh tokens (permite revocación real)
CREATE TABLE sesiones (
    id              SERIAL PRIMARY KEY,
    usuario_id      INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    refresh_token_hash CHAR(64) NOT NULL UNIQUE,  -- SHA-256 del token
    ip_origen       INET,
    user_agent      TEXT,
    emitido_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_at       TIMESTAMPTZ NOT NULL,
    revocado_at     TIMESTAMPTZ
);
CREATE INDEX idx_sesiones_usuario ON sesiones(usuario_id) WHERE revocado_at IS NULL;

-- ============================================================================
-- SECCIÓN 3 : RECURSOS FÍSICOS (quirófanos y camas)
-- ============================================================================

CREATE TABLE tipos_cama (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(20) NOT NULL UNIQUE,  -- UCI, UCIN, INTERMEDIA, GENERAL
    nombre              VARCHAR(80) NOT NULL,
    nivel_complejidad   SMALLINT NOT NULL,            -- 1 general ... 4 UCI
    codigo_snomed       VARCHAR(20),                  -- 309904001 = UCI (verificado)
    costo_dia_cop       NUMERIC(12,2),                -- caso de negocio
    activo              BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE servicios (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(20) NOT NULL UNIQUE,
    nombre      VARCHAR(80) NOT NULL,
    piso        SMALLINT,
    activo      BOOLEAN NOT NULL DEFAULT TRUE
);

-- Estados posibles: disponible | reservada | ocupada | en_proceso_alta
--                   | en_limpieza | bloqueada | contaminada | aislamiento
-- Mapean a FHIR Location.operationalStatus (HL7 v2-0116): U,O,H,C,K,I
CREATE TABLE camas (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(20) NOT NULL UNIQUE,
    tipo_cama_id        INT NOT NULL REFERENCES tipos_cama(id),
    servicio_id         INT NOT NULL REFERENCES servicios(id),
    estado              VARCHAR(20) NOT NULL DEFAULT 'disponible',
    estado_desde        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fhir_location_id    VARCHAR(64),                  -- id devuelto por HAPI
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMPTZ,
    deleted_by          INT REFERENCES usuarios(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          INT REFERENCES usuarios(id),
    CONSTRAINT ck_camas_estado CHECK (estado IN
        ('disponible','reservada','ocupada','en_proceso_alta',
         'en_limpieza','bloqueada','contaminada','aislamiento'))
);
CREATE INDEX idx_camas_estado ON camas(estado, tipo_cama_id) WHERE activo;

-- Estados: disponible | en_preparacion | en_cirugia | en_limpieza | bloqueado
CREATE TABLE quirofanos (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(20) NOT NULL UNIQUE,
    nombre              VARCHAR(80),
    servicio_id         INT REFERENCES servicios(id),
    tiene_arco_c        BOOLEAN NOT NULL DEFAULT FALSE, -- equipamiento
    tiene_circulacion_extracorporea BOOLEAN NOT NULL DEFAULT FALSE,
    estado              VARCHAR(20) NOT NULL DEFAULT 'disponible',
    estado_desde        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fhir_location_id    VARCHAR(64),
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMPTZ,
    deleted_by          INT REFERENCES usuarios(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          INT REFERENCES usuarios(id),
    CONSTRAINT ck_quirofanos_estado CHECK (estado IN
        ('disponible','en_preparacion','en_cirugia','en_limpieza','bloqueado'))
);
CREATE INDEX idx_quirofanos_estado ON quirofanos(estado) WHERE activo;

-- ============================================================================
-- SECCIÓN 4 : CATÁLOGO CLÍNICO
-- ============================================================================

-- Hallazgo de campo (D. F. De la Cruz, com. personal, 6 sep 2026):
-- el tipo de cama de recuperación depende del procedimiento.
CREATE TABLE catalogo_procedimientos (
    id                          SERIAL PRIMARY KEY,
    codigo_interno              VARCHAR(20) NOT NULL UNIQUE,
    nombre                      VARCHAR(200) NOT NULL,
    codigo_snomed               VARCHAR(20),   -- VERIFICAR en browser.ihtsdotools.org
    codigo_cups                 VARCHAR(20),   -- CUPS: estándar colombiano
    especialidad_id             INT NOT NULL REFERENCES especialidades(id),
    duracion_estimada_min       SMALLINT NOT NULL,
    duracion_desviacion_min     SMALLINT NOT NULL DEFAULT 20, -- para simulación
    tipo_cama_requerida_id      INT NOT NULL REFERENCES tipos_cama(id),
    requiere_arco_c             BOOLEAN NOT NULL DEFAULT FALSE,
    complejidad                 SMALLINT NOT NULL DEFAULT 2,  -- 1 baja .. 4 alta
    tarifa_referencia_cop       NUMERIC(12,2),                -- caso de negocio
    activo                      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE diagnosticos_cie10 (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(10) NOT NULL UNIQUE,   -- K35, I21, S72...
    descripcion VARCHAR(250) NOT NULL,
    capitulo    VARCHAR(120)
);

-- Taxonomía de causas de cancelación basada en Muñoz-Caicedo et al. (2019)
CREATE TABLE catalogo_causas_cancelacion (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(30) NOT NULL UNIQUE,
    descripcion     VARCHAR(200) NOT NULL,
    responsable     VARCHAR(20) NOT NULL,  -- paciente | prestador | asegurador
    origen          VARCHAR(20),           -- administrativo | asistencial
    evitable        BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_causa_responsable CHECK (responsable IN
        ('paciente','prestador','asegurador'))
);

-- ============================================================================
-- SECCIÓN 5 : PACIENTES  (datos sensibles -> cifrado obligatorio)
-- ============================================================================

CREATE TABLE eps (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(20) NOT NULL UNIQUE,
    nombre      VARCHAR(150) NOT NULL,
    regimen     VARCHAR(20),   -- contributivo | subsidiado | especial
    activo      BOOLEAN NOT NULL DEFAULT TRUE
);

-- La llave primaria de esta tabla es documento_bidx (el índice ciego derivado
-- de la cédula), NO un id numérico autoincremental. Así, la identidad real de
-- la persona -- no un contador arbitrario -- es lo que conecta a un paciente
-- con TODO lo demás (encuentros, observaciones, agenda, usuarios).
-- Sigue sin exponer la cédula en texto plano: documento_bidx es un HMAC-SHA256
-- irreversible, no el número real (ver docs/SEGURIDAD.md sección 3).
CREATE TABLE pacientes (
    documento_bidx          CHAR(64) PRIMARY KEY,       -- = HMAC-SHA256(cédula normalizada)
    uuid                    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    -- Identificadores directos: CIFRADOS
    tipo_documento          VARCHAR(5) NOT NULL,        -- CC, TI, CE, RC, PA
    documento_cifrado       BYTEA NOT NULL,
    nombre_cifrado          BYTEA NOT NULL,
    apellido_cifrado        BYTEA NOT NULL,
    telefono_cifrado        BYTEA,
    email_cifrado           BYTEA,
    direccion_cifrada       BYTEA,
    -- Datos clínicos/demográficos: NO cifrados (necesarios para analítica)
    fecha_nacimiento        DATE NOT NULL,
    sexo                    CHAR(1) NOT NULL,           -- M, F, O
    eps_id                  INT REFERENCES eps(id),
    tiene_comorbilidades    BOOLEAN NOT NULL DEFAULT FALSE,
    riesgo_asa              SMALLINT,                   -- clasificación ASA 1-5
    -- Trazabilidad / habeas data
    consentimiento_datos    BOOLEAN NOT NULL DEFAULT FALSE,
    consentimiento_fecha    TIMESTAMPTZ,
    fhir_patient_id         VARCHAR(64),
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at              TIMESTAMPTZ,
    deleted_by              INT REFERENCES usuarios(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              INT REFERENCES usuarios(id),
    updated_at              TIMESTAMPTZ,
    CONSTRAINT ck_pacientes_sexo CHECK (sexo IN ('M','F','O'))
);
CREATE INDEX idx_pacientes_eps  ON pacientes(eps_id) WHERE activo;
-- (ya no hace falta un índice aparte para documento_bidx: al ser PRIMARY KEY,
-- Postgres crea ese índice automáticamente)

-- FK diferida de usuarios -> pacientes (rol 'paciente')
ALTER TABLE usuarios
    ADD CONSTRAINT fk_usuarios_paciente
    FOREIGN KEY (paciente_id) REFERENCES pacientes(documento_bidx);

-- ============================================================================
-- SECCIÓN 6 : ENCUENTROS CLÍNICOS  (núcleo operativo)
-- ============================================================================

-- Mapea a FHIR Encounter.
-- class: urgencias->EMER, hospitalizacion->IMP, consulta_externa->AMB,
--        cirugia->SS/IMP  (system v3-ActCode)
CREATE TABLE encuentros (
    id                      SERIAL PRIMARY KEY,
    uuid                    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    paciente_id             CHAR(64) NOT NULL REFERENCES pacientes(documento_bidx),
    tipo                    VARCHAR(25) NOT NULL,   -- urgencias|cirugia|hospitalizacion|consulta_externa
    estado                  VARCHAR(20) NOT NULL DEFAULT 'planned',
    origen                  VARCHAR(15) NOT NULL DEFAULT 'electiva', -- electiva|urgencia
    prioridad_clinica       SMALLINT NOT NULL DEFAULT 3,  -- 1 = máxima urgencia
    nivel_triage            SMALLINT,                     -- 1-5, solo urgencias
    diagnostico_cie10_id    INT REFERENCES diagnosticos_cie10(id),
    -- Recursos asignados
    procedimiento_id        INT REFERENCES catalogo_procedimientos(id),
    quirofano_id            INT REFERENCES quirofanos(id),
    cama_id                 INT REFERENCES camas(id),
    medico_responsable_id   INT REFERENCES personal(id),
    anestesiologo_id        INT REFERENCES personal(id),
    -- Tiempos: programado vs real  <-- ALIMENTA LOS MODELOS DE PREDICCIÓN
    hora_programada_inicio  TIMESTAMPTZ,
    hora_programada_fin     TIMESTAMPTZ,
    hora_real_inicio        TIMESTAMPTZ,
    hora_real_fin           TIMESTAMPTZ,
    minutos_desviacion      INT GENERATED ALWAYS AS (
        CASE WHEN hora_real_fin IS NOT NULL AND hora_programada_fin IS NOT NULL
             THEN EXTRACT(EPOCH FROM (hora_real_fin - hora_programada_fin))::INT / 60
        END) STORED,
    -- Interoperabilidad y trazabilidad
    fhir_encounter_id       VARCHAR(64),
    observaciones_texto     TEXT,
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at              TIMESTAMPTZ,
    deleted_by              INT REFERENCES usuarios(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              INT REFERENCES usuarios(id),
    updated_at              TIMESTAMPTZ,
    CONSTRAINT ck_enc_tipo   CHECK (tipo IN
        ('urgencias','cirugia','hospitalizacion','consulta_externa')),
    CONSTRAINT ck_enc_estado CHECK (estado IN
        ('planned','arrived','triaged','in-progress','onleave','finished','cancelled')),
    CONSTRAINT ck_enc_origen CHECK (origen IN ('electiva','urgencia'))
);
CREATE INDEX idx_enc_paciente   ON encuentros(paciente_id) WHERE activo;
CREATE INDEX idx_enc_estado     ON encuentros(estado, tipo) WHERE activo;
CREATE INDEX idx_enc_programado ON encuentros(hora_programada_inicio) WHERE activo;
CREATE INDEX idx_enc_quirofano  ON encuentros(quirofano_id) WHERE activo;

-- ============================================================================
-- SECCIÓN 7 : OBSERVACIONES  (FHIR Observation, códigos LOINC)
-- ============================================================================

CREATE TABLE observaciones (
    id                  SERIAL PRIMARY KEY,
    uuid                UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    encuentro_id        INT NOT NULL REFERENCES encuentros(id),
    paciente_id         CHAR(64) NOT NULL REFERENCES pacientes(documento_bidx),
    categoria           VARCHAR(25) NOT NULL DEFAULT 'vital-signs', -- vital-signs|laboratory
    codigo_loinc        VARCHAR(20) NOT NULL,
    display_loinc       VARCHAR(150),
    valor_numerico      NUMERIC(12,3),
    valor_texto         VARCHAR(200),
    unidad_ucum         VARCHAR(20),        -- /min, mm[Hg], Cel, %
    estado              VARCHAR(20) NOT NULL DEFAULT 'final',
    es_critico          BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_hora          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    registrado_por      INT REFERENCES personal(id),
    fhir_observation_id VARCHAR(64),
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMPTZ,
    deleted_by          INT REFERENCES usuarios(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          INT REFERENCES usuarios(id),
    CONSTRAINT ck_obs_estado CHECK (estado IN
        ('registered','preliminary','final','amended','cancelled'))
);
CREATE INDEX idx_obs_encuentro ON observaciones(encuentro_id) WHERE activo;
CREATE INDEX idx_obs_loinc     ON observaciones(codigo_loinc) WHERE activo;
CREATE INDEX idx_obs_critico   ON observaciones(es_critico) WHERE activo AND es_critico;

-- ============================================================================
-- SECCIÓN 8 : CANCELACIONES Y EVENTOS  (evidencia del problema)
-- ============================================================================

CREATE TABLE cancelaciones (
    id                  SERIAL PRIMARY KEY,
    encuentro_id        INT NOT NULL REFERENCES encuentros(id),
    causa_id            INT NOT NULL REFERENCES catalogo_causas_cancelacion(id),
    detalle             TEXT,
    minutos_anticipacion INT,      -- cuánto antes de la hora programada se supo
    reprogramada        BOOLEAN NOT NULL DEFAULT FALSE,
    encuentro_nuevo_id  INT REFERENCES encuentros(id),
    costo_estimado_cop  NUMERIC(12,2),
    registrado_por      INT REFERENCES usuarios(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_canc_encuentro ON cancelaciones(encuentro_id);

-- Log inmutable de cambios de estado de recursos.
-- Fuente de verdad para: auditoría, cálculo de horas ociosas, y ML.
CREATE TABLE eventos_estado (
    id              BIGSERIAL PRIMARY KEY,
    entidad_tipo    VARCHAR(20) NOT NULL,   -- cama | quirofano | encuentro
    entidad_id      INT NOT NULL,
    estado_anterior VARCHAR(30),
    estado_nuevo    VARCHAR(30) NOT NULL,
    duracion_estado_anterior_min INT,       -- cuánto duró el estado previo
    motivo          VARCHAR(200),
    usuario_id      INT REFERENCES usuarios(id),
    origen          VARCHAR(20) NOT NULL DEFAULT 'manual', -- manual|automatico|integracion
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_evt_entidad ON eventos_estado(entidad_tipo, entidad_id, timestamp DESC);
CREATE INDEX idx_evt_ts      ON eventos_estado(timestamp DESC);

-- ============================================================================
-- SECCIÓN 9 : AUDITORÍA Y HISTORIAL (exigido por la rúbrica)
-- ============================================================================

-- Quién hizo qué y cuándo. Append-only (ver trigger de protección abajo).
CREATE TABLE log_auditoria (
    id              BIGSERIAL PRIMARY KEY,
    usuario_id      INT REFERENCES usuarios(id),
    rol_codigo      VARCHAR(40),
    entidad_tipo    VARCHAR(40) NOT NULL,
    -- VARCHAR y no INT a propósito: para 'paciente' este campo guarda
    -- documento_bidx (64 caracteres), no un id numérico. Para las demás
    -- entidades (encuentro, observacion, cama...) sigue guardando su id
    -- normal, solo que como texto.
    entidad_id      VARCHAR(64),
    operacion       VARCHAR(20) NOT NULL,   -- create|read|update|soft_delete|restore|login
    resultado       VARCHAR(15) NOT NULL DEFAULT 'exito', -- exito|denegado|error
    valor_anterior  JSONB,
    valor_nuevo     JSONB,
    ip_origen       INET,
    user_agent      TEXT,
    endpoint        VARCHAR(200),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_usuario ON log_auditoria(usuario_id, timestamp DESC);
CREATE INDEX idx_audit_entidad ON log_auditoria(entidad_tipo, entidad_id, timestamp DESC);
CREATE INDEX idx_audit_op      ON log_auditoria(operacion, timestamp DESC);

-- Historial de versiones para soft edit (conserva el valor anterior).
CREATE TABLE historial_cambios (
    id              BIGSERIAL PRIMARY KEY,
    entidad_tipo    VARCHAR(40) NOT NULL,
    -- Mismo motivo que en log_auditoria: 'paciente' guarda aquí su
    -- documento_bidx (64 caracteres), no un id numérico.
    entidad_id      VARCHAR(64) NOT NULL,
    version         INT NOT NULL,
    campo           VARCHAR(60) NOT NULL,
    valor_anterior  TEXT,
    valor_nuevo     TEXT,
    era_cifrado     BOOLEAN NOT NULL DEFAULT FALSE, -- si sí, valores van cifrados
    usuario_id      INT REFERENCES usuarios(id),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_hist_entidad ON historial_cambios(entidad_tipo, entidad_id, version DESC);

-- Protección append-only del log de auditoría: nadie puede modificar ni borrar.
CREATE OR REPLACE FUNCTION fn_auditoria_inmutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'log_auditoria es append-only: operación % no permitida', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auditoria_no_update
    BEFORE UPDATE OR DELETE ON log_auditoria
    FOR EACH ROW EXECUTE FUNCTION fn_auditoria_inmutable();

-- ============================================================================
-- SECCIÓN 10 : SOPORTE PARA FASES FUTURAS DEL SEMESTRE
-- ============================================================================

-- Consulta externa: captura la dependencia especialista <-> cirugía <-> consulta
-- (hallazgo de campo: si se atrasa una cirugía, se atrasan las consultas).
CREATE TABLE agenda_consulta_externa (
    id                      SERIAL PRIMARY KEY,
    paciente_id             CHAR(64) NOT NULL REFERENCES pacientes(documento_bidx),
    medico_general_id       INT REFERENCES personal(id),
    especialista_id         INT REFERENCES personal(id),
    modulo                  VARCHAR(20),
    hora_programada         TIMESTAMPTZ NOT NULL,
    duracion_programada_min SMALLINT NOT NULL DEFAULT 20,
    hora_real_inicio        TIMESTAMPTZ,
    hora_real_fin           TIMESTAMPTZ,
    estado                  VARCHAR(20) NOT NULL DEFAULT 'planned',
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at              TIMESTAMPTZ,
    deleted_by              INT REFERENCES usuarios(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              INT REFERENCES usuarios(id)
);
CREATE INDEX idx_consulta_especialista ON agenda_consulta_externa(especialista_id, hora_programada);

-- Predicciones generadas por los modelos (fase de IA).
CREATE TABLE predicciones (
    id                  BIGSERIAL PRIMARY KEY,
    modelo              VARCHAR(50) NOT NULL,   -- duracion_cirugia|riesgo_cancelacion|liberacion_cama
    version_modelo      VARCHAR(20),
    entidad_tipo        VARCHAR(20) NOT NULL,
    entidad_id          INT NOT NULL,
    valor_predicho      NUMERIC(12,3),
    probabilidad        NUMERIC(5,4),
    intervalo_inferior  NUMERIC(12,3),
    intervalo_superior  NUMERIC(12,3),
    features_usadas     JSONB,
    valor_real          NUMERIC(12,3),          -- se llena después -> evalúa el modelo
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_pred_entidad ON predicciones(entidad_tipo, entidad_id);
CREATE INDEX idx_pred_modelo  ON predicciones(modelo, created_at DESC);

-- Alertas generadas por el sistema (fase de agentes).
CREATE TABLE alertas (
    id              BIGSERIAL PRIMARY KEY,
    tipo            VARCHAR(40) NOT NULL,   -- capacidad_critica|conflicto_agenda|valor_critico
    severidad       VARCHAR(15) NOT NULL DEFAULT 'media', -- baja|media|alta|critica
    titulo          VARCHAR(200) NOT NULL,
    mensaje         TEXT,
    entidad_tipo    VARCHAR(20),
    entidad_id      INT,
    dirigida_a_rol  INT REFERENCES roles(id),
    dirigida_a_usuario INT REFERENCES usuarios(id),
    leida_at        TIMESTAMPTZ,
    resuelta_at     TIMESTAMPTZ,
    resuelta_por    INT REFERENCES usuarios(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_alertas_pendientes ON alertas(severidad, created_at DESC)
    WHERE resuelta_at IS NULL;

-- ============================================================================
-- SECCIÓN 11 : VISTAS PARA EL CASO DE NEGOCIO
-- ============================================================================

-- Ocupación actual por tipo de cama
CREATE OR REPLACE VIEW v_ocupacion_camas AS
SELECT
    tc.codigo                                            AS tipo_cama,
    tc.nombre,
    COUNT(*)                                             AS total,
    COUNT(*) FILTER (WHERE c.estado = 'ocupada')         AS ocupadas,
    COUNT(*) FILTER (WHERE c.estado = 'disponible')      AS disponibles,
    COUNT(*) FILTER (WHERE c.estado = 'en_limpieza')     AS en_limpieza,
    ROUND(100.0 * COUNT(*) FILTER (WHERE c.estado = 'ocupada')
          / NULLIF(COUNT(*),0), 1)                       AS pct_ocupacion
FROM camas c
JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
WHERE c.activo
GROUP BY tc.id, tc.codigo, tc.nombre, tc.nivel_complejidad
ORDER BY tc.nivel_complejidad DESC;

-- Horas ociosas de cama y su costo (el argumento de venta)
CREATE OR REPLACE VIEW v_horas_ociosas_camas AS
SELECT
    DATE_TRUNC('month', e.timestamp)                     AS mes,
    tc.codigo                                            AS tipo_cama,
    SUM(e.duracion_estado_anterior_min) / 60.0           AS horas_disponible,
    ROUND(SUM(e.duracion_estado_anterior_min) / 60.0
          * (tc.costo_dia_cop / 24), 0)                  AS costo_oportunidad_cop
FROM eventos_estado e
JOIN camas c       ON c.id = e.entidad_id
JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
WHERE e.entidad_tipo = 'cama'
  AND e.estado_anterior = 'disponible'
  AND e.duracion_estado_anterior_min IS NOT NULL
GROUP BY 1, 2, tc.costo_dia_cop
ORDER BY 1 DESC, 2;

-- Indicador de cancelación (Resolución 256/2016)
CREATE OR REPLACE VIEW v_indicador_cancelacion AS
SELECT
    DATE_TRUNC('month', e.hora_programada_inicio)        AS mes,
    COUNT(*)                                             AS programadas,
    COUNT(*) FILTER (WHERE e.estado = 'cancelled')       AS canceladas,
    ROUND(100.0 * COUNT(*) FILTER (WHERE e.estado = 'cancelled')
          / NULLIF(COUNT(*),0), 2)                       AS pct_cancelacion,
    COUNT(*) FILTER (WHERE cc.responsable = 'prestador') AS por_prestador,
    COUNT(*) FILTER (WHERE cc.evitable)                  AS evitables
FROM encuentros e
LEFT JOIN cancelaciones can ON can.encuentro_id = e.id
LEFT JOIN catalogo_causas_cancelacion cc ON cc.id = can.causa_id
WHERE e.tipo = 'cirugia' AND e.activo
GROUP BY 1
ORDER BY 1 DESC;

-- Desviación programado vs real (insumo del modelo de predicción)
-- Ocupación de camas con el paciente actual y el estado de su cirugía/encuentro.
-- Responde exactamente: "la cama UCI tal está ocupada por el paciente tal,
-- desde tal fecha, y su cirugía está en tal estado".
-- DISTINCT ON toma, por cada cama, el encuentro más reciente que la usa
-- (no existe hoy una tabla de "asignación de cama" con inicio/fin explícito,
-- así que esto es la mejor aproximación disponible sin crear una tabla nueva).
CREATE OR REPLACE VIEW v_camas_ocupacion_detalle AS
SELECT DISTINCT ON (c.id)
    c.id                        AS cama_id,
    c.codigo                    AS cama_codigo,
    tc.codigo                   AS tipo_cama,
    c.estado                    AS estado_cama,
    c.estado_desde              AS estado_cama_desde,
    e.id                        AS encuentro_id,
    e.paciente_id,
    e.estado                    AS estado_encuentro,
    e.hora_real_inicio,
    e.hora_real_fin,
    p.tipo_documento            AS paciente_tipo_documento,
    p.fecha_nacimiento          AS paciente_fecha_nacimiento,
    p.sexo                      AS paciente_sexo
FROM camas c
JOIN tipos_cama tc  ON tc.id = c.tipo_cama_id
LEFT JOIN encuentros e ON e.cama_id = c.id AND e.activo
LEFT JOIN pacientes p  ON p.documento_bidx = e.paciente_id
WHERE c.activo
ORDER BY c.id, e.hora_real_inicio DESC NULLS LAST, e.id DESC;

-- Gasto acumulado por paciente: tarifa de los procedimientos ya realizados
-- + costo estimado de las horas de cama ocupadas (costo_dia_cop / 24 x horas).
-- NO incluye el costo de cancelaciones -- eso es pérdida de la institución,
-- no un cargo al paciente; se mantiene aparte en v_horas_ociosas_camas.
CREATE OR REPLACE VIEW v_gastos_paciente AS
WITH gasto_procedimientos AS (
    SELECT
        e.paciente_id,
        COUNT(*)                       AS procedimientos_realizados,
        SUM(cp.tarifa_referencia_cop)  AS gasto_procedimientos_cop
    FROM encuentros e
    JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
    WHERE e.estado = 'finished' AND e.activo
    GROUP BY e.paciente_id
),
gasto_camas AS (
    SELECT
        e.paciente_id,
        SUM(EXTRACT(EPOCH FROM (COALESCE(e.hora_real_fin, NOW()) - e.hora_real_inicio)) / 3600.0)
            AS horas_cama_total,
        SUM(EXTRACT(EPOCH FROM (COALESCE(e.hora_real_fin, NOW()) - e.hora_real_inicio)) / 3600.0
            * (tc.costo_dia_cop / 24))
            AS gasto_estancia_cop
    FROM encuentros e
    JOIN camas c       ON c.id = e.cama_id
    JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
    WHERE e.hora_real_inicio IS NOT NULL AND e.activo
    GROUP BY e.paciente_id
)
SELECT
    p.documento_bidx                                                        AS paciente_id,
    p.tipo_documento,
    COALESCE(gp.procedimientos_realizados, 0)                               AS procedimientos_realizados,
    ROUND(COALESCE(gp.gasto_procedimientos_cop, 0), 0)                      AS gasto_procedimientos_cop,
    ROUND(COALESCE(gc.horas_cama_total, 0), 1)                              AS horas_cama_total,
    ROUND(COALESCE(gc.gasto_estancia_cop, 0), 0)                            AS gasto_estancia_cop,
    ROUND(COALESCE(gp.gasto_procedimientos_cop,0) + COALESCE(gc.gasto_estancia_cop,0), 0)
                                                                             AS gasto_total_cop
FROM pacientes p
LEFT JOIN gasto_procedimientos gp ON gp.paciente_id = p.documento_bidx
LEFT JOIN gasto_camas gc          ON gc.paciente_id = p.documento_bidx
WHERE p.activo;

CREATE OR REPLACE VIEW v_desviacion_quirurgica AS
SELECT
    cp.nombre                                            AS procedimiento,
    esp.nombre                                           AS especialidad,
    COUNT(*)                                             AS n_cirugias,
    ROUND(AVG(cp.duracion_estimada_min), 1)              AS duracion_estimada,
    ROUND(AVG(EXTRACT(EPOCH FROM (e.hora_real_fin - e.hora_real_inicio))/60)::NUMERIC, 1)
                                                         AS duracion_real_promedio,
    ROUND(AVG(e.minutos_desviacion), 1)                  AS desviacion_promedio_min
FROM encuentros e
JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
JOIN especialidades esp         ON esp.id = cp.especialidad_id
WHERE e.tipo = 'cirugia'
  AND e.hora_real_fin IS NOT NULL
  AND e.activo
GROUP BY cp.id, cp.nombre, esp.nombre, cp.duracion_estimada_min
ORDER BY desviacion_promedio_min DESC NULLS LAST;
