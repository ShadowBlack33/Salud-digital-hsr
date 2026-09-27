-- ============================================================================
-- MIGRACIÓN: la cédula (índice ciego) reemplaza el id numérico como llave
-- real de "pacientes" en TODAS las tablas relacionadas.
--
-- Preserva todos los datos existentes -- no borra ni regenera nada.
-- Se puede correr una sola vez sobre la base compartida.
-- ============================================================================
BEGIN;

-- ----------------------------------------------------------------------------
-- Paso 0 · Guardar el mapa id -> documento_bidx ANTES de tocar nada.
-- Se necesita más adelante para traducir entidad_id en log_auditoria e
-- historial_cambios (que hoy guardan el id viejo como entero).
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE _mapa_paciente AS
SELECT id, documento_bidx FROM pacientes;

-- ----------------------------------------------------------------------------
-- Paso 1 · Agregar la nueva columna (paralela) en cada tabla que referencia
-- a pacientes, y rellenarla a partir del id viejo.
-- ----------------------------------------------------------------------------
ALTER TABLE encuentros              ADD COLUMN paciente_bidx CHAR(64);
ALTER TABLE observaciones           ADD COLUMN paciente_bidx CHAR(64);
ALTER TABLE usuarios                ADD COLUMN paciente_bidx CHAR(64);
ALTER TABLE agenda_consulta_externa ADD COLUMN paciente_bidx CHAR(64);

UPDATE encuentros e   SET paciente_bidx = m.documento_bidx
    FROM _mapa_paciente m WHERE m.id = e.paciente_id;
UPDATE observaciones o SET paciente_bidx = m.documento_bidx
    FROM _mapa_paciente m WHERE m.id = o.paciente_id;
UPDATE usuarios u      SET paciente_bidx = m.documento_bidx
    FROM _mapa_paciente m WHERE m.id = u.paciente_id;
UPDATE agenda_consulta_externa a SET paciente_bidx = m.documento_bidx
    FROM _mapa_paciente m WHERE m.id = a.paciente_id;

-- Verificación de seguridad: si algún encuentro/observación quedó sin
-- traducir, es que había un paciente_id huérfano -- mejor frenar aquí
-- que seguir con datos incompletos.
DO $$
DECLARE huerfanos INT;
BEGIN
    SELECT COUNT(*) INTO huerfanos FROM encuentros WHERE paciente_id IS NOT NULL AND paciente_bidx IS NULL;
    IF huerfanos > 0 THEN
        RAISE EXCEPTION 'Hay % encuentros con paciente_id que no se pudo traducir. Migración detenida.', huerfanos;
    END IF;
    SELECT COUNT(*) INTO huerfanos FROM observaciones WHERE paciente_id IS NOT NULL AND paciente_bidx IS NULL;
    IF huerfanos > 0 THEN
        RAISE EXCEPTION 'Hay % observaciones con paciente_id que no se pudo traducir. Migración detenida.', huerfanos;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- Paso 2 · Quitar las llaves foráneas viejas (apuntan a pacientes.id),
-- sea cual sea el nombre real que Postgres les haya puesto.
-- ----------------------------------------------------------------------------
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT conname, conrelid::regclass AS tabla
        FROM pg_constraint
        WHERE confrelid = 'pacientes'::regclass AND contype = 'f'
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tabla, r.conname);
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- Paso 3 · Botar la columna vieja (INT) y poner la nueva en su lugar,
-- con el mismo nombre de siempre: paciente_id.
-- ----------------------------------------------------------------------------
ALTER TABLE encuentros              DROP COLUMN paciente_id;
ALTER TABLE encuentros              RENAME COLUMN paciente_bidx TO paciente_id;
ALTER TABLE encuentros              ALTER COLUMN paciente_id SET NOT NULL;

ALTER TABLE observaciones           DROP COLUMN paciente_id;
ALTER TABLE observaciones           RENAME COLUMN paciente_bidx TO paciente_id;
ALTER TABLE observaciones           ALTER COLUMN paciente_id SET NOT NULL;

ALTER TABLE usuarios                DROP COLUMN paciente_id;
ALTER TABLE usuarios                RENAME COLUMN paciente_bidx TO paciente_id;
-- (usuarios.paciente_id sigue siendo NULLABLE a propósito: la mayoría de
-- cuentas -médicos, admin, etc.- no están ligadas a un paciente)

ALTER TABLE agenda_consulta_externa DROP COLUMN paciente_id;
ALTER TABLE agenda_consulta_externa RENAME COLUMN paciente_bidx TO paciente_id;
ALTER TABLE agenda_consulta_externa ALTER COLUMN paciente_id SET NOT NULL;

-- ----------------------------------------------------------------------------
-- Paso 4 · Ahora que nada apunta a pacientes.id, esa columna puede
-- desaparecer y documento_bidx se convierte en la llave primaria real.
-- ----------------------------------------------------------------------------
ALTER TABLE pacientes DROP CONSTRAINT pacientes_pkey;
ALTER TABLE pacientes DROP COLUMN id;
ALTER TABLE pacientes ADD PRIMARY KEY (documento_bidx);

-- ----------------------------------------------------------------------------
-- Paso 5 · Las llaves foráneas nuevas, apuntando a documento_bidx.
-- ----------------------------------------------------------------------------
ALTER TABLE encuentros
    ADD CONSTRAINT encuentros_paciente_id_fkey
    FOREIGN KEY (paciente_id) REFERENCES pacientes(documento_bidx);
ALTER TABLE observaciones
    ADD CONSTRAINT observaciones_paciente_id_fkey
    FOREIGN KEY (paciente_id) REFERENCES pacientes(documento_bidx);
ALTER TABLE usuarios
    ADD CONSTRAINT fk_usuarios_paciente
    FOREIGN KEY (paciente_id) REFERENCES pacientes(documento_bidx);
ALTER TABLE agenda_consulta_externa
    ADD CONSTRAINT agenda_consulta_externa_paciente_id_fkey
    FOREIGN KEY (paciente_id) REFERENCES pacientes(documento_bidx);

CREATE INDEX IF NOT EXISTS idx_enc_paciente ON encuentros(paciente_id) WHERE activo;

-- ----------------------------------------------------------------------------
-- Paso 6 · Ensanchar entidad_id en auditoría/historial (hoy INT, y
-- 'paciente' ya no cabe ahí como número) y traducir lo que ya existía,
-- usando el mapa del Paso 0.
-- ----------------------------------------------------------------------------
ALTER TABLE log_auditoria     ALTER COLUMN entidad_id TYPE VARCHAR(64);
ALTER TABLE historial_cambios ALTER COLUMN entidad_id TYPE VARCHAR(64);

UPDATE log_auditoria la SET entidad_id = m.documento_bidx
    FROM _mapa_paciente m
    WHERE la.entidad_tipo = 'paciente' AND la.entidad_id = m.id::text;

UPDATE historial_cambios hc SET entidad_id = m.documento_bidx
    FROM _mapa_paciente m
    WHERE hc.entidad_tipo = 'paciente' AND hc.entidad_id = m.id::text;

COMMIT;
