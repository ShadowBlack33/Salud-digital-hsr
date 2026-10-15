-- ============================================================================
-- 14 · Sistema reactivo: bandeja de notificaciones y eventos recibidos desde
--      FHIR (R17, R18, R19, R21)
--
-- notificaciones  La bandeja persistente de cada usuario. El canal en vivo
--                 (SSE) solo empuja lo que aquí ya quedó guardado: si el
--                 usuario estaba desconectado, lo ve al volver.
--                 No guarda nombre, documento ni texto clínico libre.
-- Las alertas críticas (R20) NO se crean aquí: viven en la tabla `alertas` que
-- extiende db/13_ia.sql (módulo de IA). Esta migración no depende de ella.
-- eventos_fhir    Registro de lo que HAPI avisó por la Subscription. Su llave
--                 única evita reaccionar dos veces a la misma Observation
--                 cuando HAPI reintenta la entrega.
--
-- Se puede correr más de una vez.
--   python scripts/aplicar_sql.py db/14_notificaciones.sql
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
