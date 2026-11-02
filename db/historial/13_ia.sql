-- ============================================================================
-- 13 · Inteligencia artificial: reportes con aprobación clínica y alertas
--      críticas (R10, R12, R20)
--
-- El reparto la llamaba 10_ia.sql, pero los números 08 a 12 ya están usados.
--
--  · reportes_ia: el análisis nace 'pendiente' y NO entra a la historia
--    clínica hasta que un medico o especialista lo aprueba. El rechazado no
--    se borra: queda como evidencia (R10). Dos triggers lo garantizan también
--    en la base, por si algún código se salta la API:
--      - nadie puede borrar un reporte;
--      - un reporte aprobado o rechazado ya no cambia de estado.
--  · payload_enviado guarda el JSON EXACTO que recibió el modelo (R12), para
--    poder demostrar que nunca viajaron datos personales.
--  · alertas (tabla del Corte 1) gana estado, reconocimiento y escalamiento
--    (R20). El "nivel" que pide el contrato sale de la columna severidad.
--
-- Permisos (los lee el JWT al iniciar sesión: hay que volver a entrar
-- después de aplicar esta migración para que el token los traiga):
--   ia:create      medico, especialista (sobre sus pacientes)      -> analizar
--   ia:read        medico, especialista (sus pacientes); paciente (self, en
--                  la API solo ve los aprobados); admin (all)
--   ia:approve     medico, especialista                             -> aprobar/rechazar
--   alerta:read    medico, especialista (las suyas); admin (all, por el escalamiento)
--   alerta:update  medico, especialista                             -> reconocer
-- contable no recibe ninguno (403 en todo lo clínico).
--
-- Se puede correr más de una vez.
--   python scripts/aplicar_sql.py db/13_ia.sql
-- ============================================================================
BEGIN;

-- ---------------------------------------------------------------- reportes_ia
CREATE TABLE IF NOT EXISTS reportes_ia (
    id               BIGSERIAL PRIMARY KEY,
    paciente_id      CHAR(64) NOT NULL REFERENCES pacientes(documento_bidx),
    creado_por       INT NOT NULL REFERENCES usuarios(id),
    estado           VARCHAR(12) NOT NULL DEFAULT 'pendiente',
    resultado        JSONB,                      -- respuesta completa del servicio ml
    probabilidad     NUMERIC(5,4),
    critico          BOOLEAN NOT NULL DEFAULT FALSE,
    payload_enviado  JSONB NOT NULL,             -- lo que recibió el modelo, tal cual (R12)
    modelo_version   VARCHAR(30),
    observaciones    TEXT,
    revisado_por     INT REFERENCES usuarios(id),
    revisado_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_rep_estado CHECK (estado IN ('pendiente','aprobado','rechazado')),
    CONSTRAINT ck_rep_probabilidad CHECK (probabilidad IS NULL OR probabilidad BETWEEN 0 AND 1),
    -- Un reporte revisado siempre dice quién y cuándo
    CONSTRAINT ck_rep_revision CHECK (
        (estado = 'pendiente' AND revisado_por IS NULL AND revisado_at IS NULL)
     OR (estado <> 'pendiente' AND revisado_por IS NOT NULL AND revisado_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_rep_paciente ON reportes_ia(paciente_id, estado, created_at DESC);
-- Contador "reportes_por_revisar" de R18: pendientes que pidió cada clínico
CREATE INDEX IF NOT EXISTS idx_rep_pendientes ON reportes_ia(creado_por) WHERE estado = 'pendiente';

CREATE OR REPLACE FUNCTION fn_reportes_ia_inmutables() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Los reportes de IA no se borran (R10): queda como evidencia el reporte %', OLD.id;
    END IF;
    IF OLD.estado <> 'pendiente' AND NEW.estado IS DISTINCT FROM OLD.estado THEN
        RAISE EXCEPTION 'El reporte % ya está % y no puede cambiar de estado', OLD.id, OLD.estado;
    END IF;
    IF NEW.payload_enviado IS DISTINCT FROM OLD.payload_enviado THEN
        RAISE EXCEPTION 'El payload enviado al modelo no se modifica (reporte %)', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reportes_ia_inmutables ON reportes_ia;
CREATE TRIGGER trg_reportes_ia_inmutables
    BEFORE UPDATE OR DELETE ON reportes_ia
    FOR EACH ROW EXECUTE FUNCTION fn_reportes_ia_inmutables();

-- ---------------------------------------------------------------- alertas (R20)
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS paciente_id         CHAR(64) REFERENCES pacientes(documento_bidx);
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS estado              VARCHAR(12) NOT NULL DEFAULT 'activa';
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS nota_reconocimiento TEXT;
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS reconocida_por      INT REFERENCES usuarios(id);
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS reconocida_at       TIMESTAMPTZ;
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS escalada_at         TIMESTAMPTZ;
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS reporte_id          BIGINT REFERENCES reportes_ia(id);

DO $$ BEGIN
    ALTER TABLE alertas ADD CONSTRAINT ck_alerta_estado CHECK (estado IN ('activa','reconocida'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Las alertas del Corte 1 que ya estaban resueltas no deben aparecer activas
UPDATE alertas SET estado = 'reconocida'
WHERE estado = 'activa' AND resuelta_at IS NOT NULL;

-- Bandeja del clínico y búsqueda del escalamiento (activas más viejas que N minutos)
CREATE INDEX IF NOT EXISTS idx_alerta_activas ON alertas(dirigida_a_usuario, created_at)
    WHERE estado = 'activa';
-- Una alerta por reporte como máximo (si se reintenta el análisis no se duplica)
CREATE UNIQUE INDEX IF NOT EXISTS uq_alerta_reporte ON alertas(reporte_id) WHERE reporte_id IS NOT NULL;

-- ---------------------------------------------------------------- permisos
INSERT INTO permisos (codigo, recurso, accion, alcance, descripcion) VALUES
('ia:create:assigned',     'ia',     'create',  'assigned', 'Ejecutar el análisis de IA sobre sus pacientes'),
('ia:read:assigned',       'ia',     'read',    'assigned', 'Ver los reportes de IA de sus pacientes'),
('ia:read:self',           'ia',     'read',    'self',     'Ver sus propios reportes de IA aprobados'),
('ia:read:all',            'ia',     'read',    'all',      'Ver todos los reportes de IA'),
('ia:approve:assigned',    'ia',     'approve', 'assigned', 'Aprobar o rechazar reportes de IA de sus pacientes'),
('alerta:read:assigned',   'alerta', 'read',    'assigned', 'Ver las alertas críticas dirigidas a él'),
('alerta:read:all',        'alerta', 'read',    'all',      'Ver todas las alertas críticas'),
('alerta:update:assigned', 'alerta', 'update',  'assigned', 'Reconocer las alertas críticas dirigidas a él')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r JOIN permisos p ON
     (r.codigo IN ('medico', 'especialista') AND p.codigo IN (
        'ia:create:assigned', 'ia:read:assigned', 'ia:approve:assigned',
        'alerta:read:assigned', 'alerta:update:assigned'))
  OR (r.codigo = 'paciente' AND p.codigo = 'ia:read:self')
  OR (r.codigo = 'admin'    AND p.codigo IN ('ia:read:all', 'alerta:read:all'))
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

COMMIT;
