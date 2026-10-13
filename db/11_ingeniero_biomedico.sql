-- ============================================================================
-- 11 · Perfil de ingeniería biomédica
--
-- Res. 4816/2008 (tecnovigilancia) exige un responsable de los dispositivos
-- médicos; Res. 3100/2019 exige mantenimiento preventivo de equipos.
-- Este perfil ve el estado de camas y quirófanos y puede sacarlos de servicio
-- (bloquear con motivo, p. ej. "mantenimiento correctivo arco en C"), pero NO
-- ve pacientes: no hace parte del equipo de salud (Res. 1995/1999 art. 14).
-- La API oculta nombre, documento y diagnóstico a quien no tiene paciente:read.
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

DELETE FROM roles_permisos WHERE rol_id = (SELECT id FROM roles WHERE codigo = 'ingeniero_biomedico');
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
 WHERE r.codigo = 'ingeniero_biomedico'
   AND p.codigo IN ('cama:read:all', 'cama:update:all', 'quirofano:read:all', 'quirofano:update:all')
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('usuarios', 'id'), (SELECT COALESCE(MAX(id), 1) FROM usuarios));
INSERT INTO usuarios (username, password_hash, rol_id, personal_id, debe_cambiar_password)
SELECT 'biomedico01',
       (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'ingeniero_biomedico'),
       NULL, FALSE
WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE username = 'biomedico01');

COMMIT;
