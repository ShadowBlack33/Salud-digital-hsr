-- ============================================================================
-- 10 · Remisiones entre médicos (R08)
--
-- El médico remite un paciente a un especialista con un motivo; el
-- especialista lo ve en su bandeja y lo acepta o rechaza, y la cierra como
-- atendida. Mientras está pendiente o aceptada, el paciente cuenta como "suyo"
-- para el especialista (app/core/deps.py: pacientes_asignados_subq); al
-- rechazarla pierde el acceso, y al atenderla lo conserva solo unos días.
-- Un paciente o un contable no tienen ningún permiso sobre remisiones (403).
--
-- Se puede correr más de una vez.
--   python scripts/aplicar_sql.py db/10_remisiones.sql
-- ============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS remisiones (
    id                  SERIAL PRIMARY KEY,
    paciente_id         CHAR(64) NOT NULL REFERENCES pacientes(documento_bidx),
    medico_id           INT REFERENCES personal(id),          -- quien remite (personal)
    remitido_por        INT NOT NULL REFERENCES usuarios(id), -- cuenta que remitió
    especialista_id     INT NOT NULL REFERENCES personal(id), -- a quién
    motivo              TEXT NOT NULL,
    prioridad           VARCHAR(12) NOT NULL DEFAULT 'prioritaria',
    estado              VARCHAR(12) NOT NULL DEFAULT 'pendiente',
    respuesta           TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    aceptada_at         TIMESTAMPTZ,
    aceptada_por        INT REFERENCES usuarios(id),
    CONSTRAINT ck_rem_estado CHECK (estado IN ('pendiente','aceptada','rechazada','atendida')),
    CONSTRAINT ck_rem_prioridad CHECK (prioridad IN ('rutinaria','prioritaria','urgente'))
);
-- Cierre: rechazo o atención. Desde cerrada_at corre la vigencia del acceso
-- del especialista a la ficha (REMISION_ACCESO_DIAS, 7 por defecto).
ALTER TABLE remisiones ADD COLUMN IF NOT EXISTS cerrada_at  TIMESTAMPTZ;
ALTER TABLE remisiones ADD COLUMN IF NOT EXISTS cerrada_por INT REFERENCES usuarios(id);

CREATE INDEX IF NOT EXISTS idx_rem_especialista ON remisiones(especialista_id, estado);
CREATE INDEX IF NOT EXISTS idx_rem_paciente ON remisiones(paciente_id);

INSERT INTO permisos (codigo, recurso, accion, alcance, descripcion) VALUES
('remision:create:all',      'remision','create','all','Remitir pacientes a especialista'),
('remision:read:all',        'remision','read','all','Ver todas las remisiones'),
('remision:read:assigned',   'remision','read','assigned','Ver las remisiones que envió o recibió'),
('remision:update:assigned', 'remision','update','assigned','Aceptar o rechazar las remisiones recibidas')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r JOIN permisos p ON
     (r.codigo = 'medico'       AND p.codigo IN ('remision:create:all', 'remision:read:assigned'))
  OR (r.codigo = 'especialista' AND p.codigo IN ('remision:create:all', 'remision:read:assigned', 'remision:update:assigned'))
  OR (r.codigo = 'admin'        AND p.codigo IN ('remision:create:all', 'remision:read:all', 'remision:update:assigned'))
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

COMMIT;
