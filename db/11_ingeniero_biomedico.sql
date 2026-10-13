-- ============================================================================
-- 11 · Perfil de ingeniería biomédica
--
-- Res. 4816/2008 (tecnovigilancia) exige un responsable de los dispositivos
-- médicos; Res. 3100/2019 exige mantenimiento preventivo de equipos.
-- Su función en Pulso es una sola: cuando un equipo falla o entra a
-- mantenimiento, sacar de servicio la cama o el quirófano donde está, y
-- devolverlo cuando quede reparado (pasa a limpieza; enfermería lo habilita).
-- Cada salida queda en `fuera_servicio` (equipo, tipo, descripción, quién,
-- desde y hasta cuándo). No puede hacer ningún otro cambio de estado (no tiene
-- cama:update ni quirofano:update) y NO ve pacientes: no hace parte del
-- equipo de salud (Res. 1995/1999 art. 14).
--
-- Cuenta de demostración: biomedico01 (misma clave de demostración que admin).
-- Se puede correr más de una vez.
--   python scripts/aplicar_sql.py db/11_ingeniero_biomedico.sql
-- ============================================================================
BEGIN;

INSERT INTO roles (codigo, nombre, descripcion, es_asistencial, es_cuenta_tecnica, nivel_jerarquico)
SELECT 'ingeniero_biomedico', 'Ingeniero(a) biomédico(a)',
       'Gestión de tecnología biomédica: disponibilidad y mantenimiento de camas, quirófanos y equipos. Sin acceso a datos clínicos.',
       FALSE, FALSE, 2
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE codigo = 'ingeniero_biomedico');

CREATE TABLE IF NOT EXISTS fuera_servicio (
    id               SERIAL PRIMARY KEY,
    recurso_tipo     VARCHAR(10) NOT NULL CHECK (recurso_tipo IN ('cama', 'quirofano')),
    recurso_id       INT NOT NULL,
    equipo           VARCHAR(120) NOT NULL,                 -- p. ej. "Ventilador", "Arco en C"
    tipo             VARCHAR(30) NOT NULL CHECK (tipo IN ('falla', 'mantenimiento_preventivo', 'mantenimiento_correctivo')),
    descripcion      TEXT NOT NULL,
    estado_anterior  VARCHAR(30),
    inicio           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fin              TIMESTAMPTZ,
    nota_cierre      TEXT,
    reportado_por    INT NOT NULL REFERENCES usuarios(id),
    cerrado_por      INT REFERENCES usuarios(id)
);
-- Un recurso no puede tener dos salidas de servicio abiertas a la vez.
CREATE UNIQUE INDEX IF NOT EXISTS ux_fuera_servicio_abierto
    ON fuera_servicio (recurso_tipo, recurso_id) WHERE fin IS NULL;

INSERT INTO permisos (codigo, recurso, accion, alcance, descripcion) VALUES
('equipo:read:all',   'equipo', 'read',   'all', 'Ver equipos fuera de servicio'),
('equipo:update:all', 'equipo', 'update', 'all', 'Sacar de servicio y devolver camas o quirófanos por equipo biomédico')
ON CONFLICT (codigo) DO NOTHING;

DELETE FROM roles_permisos WHERE rol_id = (SELECT id FROM roles WHERE codigo = 'ingeniero_biomedico');
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
 WHERE r.codigo = 'ingeniero_biomedico'
   AND p.codigo IN ('cama:read:all', 'quirofano:read:all', 'equipo:read:all', 'equipo:update:all')
ON CONFLICT (rol_id, permiso_id) DO NOTHING;
-- El admin y el coordinador pueden consultar el historial.
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
 WHERE r.codigo IN ('admin', 'coordinador') AND p.codigo = 'equipo:read:all'
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('usuarios', 'id'), (SELECT COALESCE(MAX(id), 1) FROM usuarios));
INSERT INTO usuarios (username, password_hash, rol_id, personal_id, debe_cambiar_password)
SELECT 'biomedico01',
       (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'ingeniero_biomedico'),
       NULL, FALSE
WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE username = 'biomedico01');

-- Sesiones abiertas de biomedico01 con permisos viejos.
UPDATE sesiones SET revocado_at = NOW()
 WHERE revocado_at IS NULL AND usuario_id = (SELECT id FROM usuarios WHERE username = 'biomedico01');

COMMIT;
