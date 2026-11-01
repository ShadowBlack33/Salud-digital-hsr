-- ============================================================================
-- 16 · Ajustes de la revisión del Corte 2
--
--   · RAG por perfil: cada guía declara a qué perfiles va (rag_fragmentos.audiencia).
--   · Alertas: ya no se escalan al admin; el coordinador y el admin ven un
--     contador de alertas sin atender por médico (alerta:supervisar:all).
--   · Remisiones: el médico pide una especialidad y dice para qué la necesita
--     (tipo_solicitud); el sistema reparte la carga entre los especialistas.
--     El especialista ya no rechaza.
--   · Resultados externos por FHIR: se guardan en observaciones (origen
--     'fhir_externo'); pueden no tener encuentro.
--
-- Ya está incluida en db/esquema_completo.sql. Para una base creada antes de
-- este cambio (la compartida en Neon, si no se reinicia):
--   python scripts/aplicar_sql.py db/16_perfiles_rag_remisiones_fhir.sql
-- Se puede correr más de una vez.
-- ============================================================================
BEGIN;

-- ------------------------------------------------------------------ RAG
-- Perfiles (roles.codigo) que pueden recuperar el fragmento. NULL en las
-- historias: esas se filtran por paciente con el permiso ia:read.
ALTER TABLE rag_fragmentos ADD COLUMN IF NOT EXISTS audiencia TEXT[];
CREATE INDEX IF NOT EXISTS ix_rag_frag_audiencia ON rag_fragmentos USING gin (audiencia);

-- ------------------------------------------------------------------ alertas
INSERT INTO permisos (codigo, recurso, accion, alcance, descripcion) VALUES
('alerta:supervisar:all', 'alerta', 'supervisar', 'all',
 'Ver cuántas alertas críticas tiene sin atender cada médico (sin datos del paciente)')
ON CONFLICT (codigo) DO NOTHING;
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r JOIN permisos p ON p.codigo = 'alerta:supervisar:all'
WHERE r.codigo IN ('admin', 'coordinador')
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

-- ------------------------------------------------------------------ remisiones
ALTER TABLE remisiones ADD COLUMN IF NOT EXISTS especialidad_id INT REFERENCES especialidades(id);
ALTER TABLE remisiones ADD COLUMN IF NOT EXISTS tipo_solicitud VARCHAR(20);
ALTER TABLE remisiones DROP CONSTRAINT IF EXISTS ck_rem_tipo_solicitud;
ALTER TABLE remisiones ADD CONSTRAINT ck_rem_tipo_solicitud CHECK (tipo_solicitud IS NULL OR tipo_solicitud IN
    ('valoracion', 'diagnostico', 'tratamiento', 'procedimiento', 'seguimiento'));
-- 'rechazada' se conserva en el CHECK de estado solo por las remisiones viejas.
UPDATE permisos SET descripcion = 'Aceptar y atender las remisiones recibidas'
 WHERE codigo = 'remision:update:assigned';
CREATE INDEX IF NOT EXISTS idx_rem_carga ON remisiones(especialista_id) WHERE estado IN ('pendiente', 'aceptada');

-- ------------------------------------------------------------------ observaciones externas
ALTER TABLE observaciones ADD COLUMN IF NOT EXISTS origen VARCHAR(15) NOT NULL DEFAULT 'interno';
ALTER TABLE observaciones DROP CONSTRAINT IF EXISTS ck_obs_origen;
ALTER TABLE observaciones ADD CONSTRAINT ck_obs_origen CHECK (origen IN ('interno', 'fhir_externo'));
-- Un resultado de laboratorio externo puede llegar sin un encuentro abierto.
ALTER TABLE observaciones ALTER COLUMN encuentro_id DROP NOT NULL;
ALTER TABLE observaciones DROP CONSTRAINT IF EXISTS ck_obs_encuentro;
ALTER TABLE observaciones ADD CONSTRAINT ck_obs_encuentro CHECK (encuentro_id IS NOT NULL OR origen = 'fhir_externo');
-- La misma Observation de FHIR se guarda una sola vez.
CREATE UNIQUE INDEX IF NOT EXISTS ux_obs_fhir_externa ON observaciones(fhir_observation_id)
    WHERE origen = 'fhir_externo';

-- Los tokens llevan los permisos dentro: se cierran las sesiones abiertas.
UPDATE sesiones SET revocado_at = NOW() WHERE revocado_at IS NULL;

COMMIT;
