-- ============================================================================
-- 13 · Sistema reactivo: bandeja de notificaciones, alertas críticas y
--      eventos recibidos desde FHIR (R17, R18, R19, R20, R21)
--
-- notificaciones  La bandeja persistente de cada usuario. El canal en vivo
--                 (SSE) solo empuja lo que aquí ya quedó guardado: si el
--                 usuario estaba desconectado, lo ve al volver.
--                 No guarda nombre, documento ni texto clínico libre.
-- alertas_criticas  Alertas críticas del modelo (R20). La escribe el módulo de
--                 IA; el escalamiento por tiempo lo hace el servidor
--                 (app/services/escalamiento.py), no el front. Es distinta de
--                 la tabla `alertas` del Corte 1 (capacidad, conflictos de
--                 agenda), que sigue igual.
-- eventos_fhir    Registro de lo que HAPI avisó por la Subscription. Su llave
--                 única evita reaccionar dos veces a la misma Observation
--                 cuando HAPI reintenta la entrega.
--
-- Se puede correr más de una vez.
--   python scripts/aplicar_sql.py db/13_notificaciones.sql
-- ============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS notificaciones (
    id           BIGSERIAL PRIMARY KEY,
    usuario_id   INT NOT NULL REFERENCES usuarios(id),
    tipo         VARCHAR(40) NOT NULL,
    mensaje      TEXT NOT NULL,
    paciente_id  CHAR(64) REFERENCES pacientes(documento_bidx),
    datos        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- ids del hecho: remision_id, alerta_id...
    leida        BOOLEAN NOT NULL DEFAULT FALSE,
    leida_at     TIMESTAMPTZ,
    fecha        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_usuario ON notificaciones(usuario_id, leida, fecha DESC);

CREATE TABLE IF NOT EXISTS alertas_criticas (
    id              SERIAL PRIMARY KEY,
    paciente_id     CHAR(64) NOT NULL REFERENCES pacientes(documento_bidx),
    usuario_id      INT NOT NULL REFERENCES usuarios(id),    -- clínico responsable
    nivel           VARCHAR(12) NOT NULL DEFAULT 'critico',
    mensaje         TEXT NOT NULL,
    reporte_id      INT,                                     -- reporte de IA que la originó
    estado          VARCHAR(12) NOT NULL DEFAULT 'activa',
    creada_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reconocida_at   TIMESTAMPTZ,
    reconocida_por  INT REFERENCES usuarios(id),
    nota            TEXT,                                    -- nota del reconocimiento
    escalada_at     TIMESTAMPTZ,                             -- cuándo se escaló al admin
    CONSTRAINT ck_alerta_estado CHECK (estado IN ('activa', 'reconocida'))
);
CREATE INDEX IF NOT EXISTS idx_alertas_crit_usuario ON alertas_criticas(usuario_id, estado);
CREATE INDEX IF NOT EXISTS idx_alertas_crit_activas ON alertas_criticas(creada_at) WHERE estado = 'activa';

CREATE TABLE IF NOT EXISTS eventos_fhir (
    id            BIGSERIAL PRIMARY KEY,
    recurso_tipo  VARCHAR(30) NOT NULL,
    recurso_id    VARCHAR(64) NOT NULL,
    version       VARCHAR(20) NOT NULL DEFAULT '',
    paciente_id   CHAR(64),
    resultado     VARCHAR(20) NOT NULL DEFAULT 'procesado',  -- procesado | sin_paciente | origen_api
    recibido_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_evento_fhir UNIQUE (recurso_tipo, recurso_id, version)
);

COMMIT;
