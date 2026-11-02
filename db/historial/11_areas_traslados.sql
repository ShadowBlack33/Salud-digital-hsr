-- ============================================================================
-- 11 · Áreas de enfermería, traslados entre áreas y alta médica
--
--  · Cada enfermero(a) jefe tiene un área a cargo (usuarios.servicio_id): solo
--    asigna camas de su área. El admin no tiene área: ve y opera todas.
--  · Traslado entre áreas: el jefe de origen (p. ej. Urgencias) revisa la
--    disponibilidad del área destino (p. ej. UCI Adultos) y le envía la
--    solicitud; el jefe de destino la acepta eligiendo la cama, o la rechaza
--    con motivo.
--  · El alta la da solo el médico tratante, con tipo de egreso y motivo. La
--    cama queda "en proceso de alta" hasta que enfermería confirma la salida.
--
-- Cuentas de demostración (clave de demostración): jefe_urg, jefe_uci,
-- jefe_ucip, jefe_piso4, jefe_piso5. jefe01 queda a cargo de Cirugía.
-- Se puede correr más de una vez.
--   python scripts/aplicar_sql.py db/11_areas_traslados.sql
-- ============================================================================
BEGIN;

-- Restos del perfil de ingeniería biomédica que se probó y se descartó.
UPDATE usuarios SET activo = FALSE WHERE username = 'biomedico01';
DELETE FROM roles_permisos WHERE permiso_id IN (SELECT id FROM permisos WHERE recurso = 'equipo');
DELETE FROM permisos WHERE recurso = 'equipo';
DROP TABLE IF EXISTS fuera_servicio;

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS servicio_id INT REFERENCES servicios(id);

CREATE TABLE IF NOT EXISTS traslados (
    id                   SERIAL PRIMARY KEY,
    paciente_id          CHAR(64) NOT NULL REFERENCES pacientes(documento_bidx),
    encuentro_origen_id  INT NOT NULL REFERENCES encuentros(id),
    servicio_origen_id   INT NOT NULL REFERENCES servicios(id),
    servicio_destino_id  INT NOT NULL REFERENCES servicios(id),
    motivo               TEXT NOT NULL,
    prioridad            VARCHAR(12) NOT NULL DEFAULT 'prioritaria'
                         CHECK (prioridad IN ('rutinaria', 'prioritaria', 'urgente')),
    estado               VARCHAR(12) NOT NULL DEFAULT 'pendiente'
                         CHECK (estado IN ('pendiente', 'aceptado', 'rechazado', 'cancelado')),
    cama_destino_id      INT REFERENCES camas(id),
    respuesta            TEXT,
    solicitado_por       INT NOT NULL REFERENCES usuarios(id),
    resuelto_por         INT REFERENCES usuarios(id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resuelto_at          TIMESTAMPTZ
);
-- Un paciente no puede tener dos traslados abiertos a la vez.
CREATE UNIQUE INDEX IF NOT EXISTS ux_traslado_abierto ON traslados (paciente_id) WHERE estado = 'pendiente';
CREATE INDEX IF NOT EXISTS idx_traslado_destino ON traslados (servicio_destino_id, estado);

INSERT INTO permisos (codigo, recurso, accion, alcance, descripcion) VALUES
('alta:create:assigned', 'alta', 'create', 'assigned', 'Dar de alta a sus pacientes (médico tratante)'),
('alta:create:all',      'alta', 'create', 'all',      'Dar de alta a cualquier paciente')
ON CONFLICT (codigo) DO NOTHING;
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r JOIN permisos p ON
     (r.codigo IN ('medico', 'especialista') AND p.codigo = 'alta:create:assigned')
  OR (r.codigo = 'admin' AND p.codigo = 'alta:create:all')
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

-- Áreas de las cuentas de demostración.
UPDATE usuarios SET servicio_id = (SELECT id FROM servicios WHERE codigo = 'CIR') WHERE username = 'jefe01';
SELECT setval(pg_get_serial_sequence('usuarios', 'id'), (SELECT COALESCE(MAX(id), 1) FROM usuarios));
INSERT INTO usuarios (username, password_hash, rol_id, personal_id, servicio_id, debe_cambiar_password)
SELECT v.usuario, (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'enfermero_jefe'), NULL,
       (SELECT id FROM servicios WHERE codigo = v.servicio), FALSE
FROM (VALUES ('jefe_urg', 'URG'), ('jefe_uci', 'UCI_ADU'), ('jefe_ucip', 'UCI_PED'),
             ('jefe_piso4', 'HOSP_1'), ('jefe_piso5', 'HOSP_2')) AS v(usuario, servicio)
WHERE NOT EXISTS (SELECT 1 FROM usuarios u WHERE u.username = v.usuario);
UPDATE usuarios u SET servicio_id = s.id
  FROM (VALUES ('jefe_urg', 'URG'), ('jefe_uci', 'UCI_ADU'), ('jefe_ucip', 'UCI_PED'),
               ('jefe_piso4', 'HOSP_1'), ('jefe_piso5', 'HOSP_2')) AS v(usuario, servicio)
  JOIN servicios s ON s.codigo = v.servicio
 WHERE u.username = v.usuario;

-- Sesiones abiertas con permisos viejos (médico y especialista ganan "alta").
UPDATE sesiones SET revocado_at = NOW() WHERE revocado_at IS NULL;
COMMIT;
