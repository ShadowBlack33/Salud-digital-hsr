-- ============================================================================
-- 08 · Roles del Corte 2 (R01)
--
-- El enunciado del Corte 2 exige cinco roles con estos códigos exactos:
--   admin, medico, especialista, paciente, contable
-- admin y paciente ya existen. Este archivo AGREGA los otros tres sin tocar
-- los 14 roles del Corte 1 (el sistema heredado debe seguir funcionando y
-- test_e2e.py no debe romperse).
--
-- Es seguro sobre la base compartida y se puede correr más de una vez:
-- todo usa ON CONFLICT DO NOTHING o NOT EXISTS.
--
-- Requisito previo: catálogos (02) y datos (03) ya cargados, porque las
-- cuentas de prueba reutilizan el hash de 'admin' y el personal existente.
--
-- Uso:
--   python scripts/aplicar_sql.py db/08_roles_corte2.sql
-- ============================================================================

-- ---------------------------------------------------------------- roles
INSERT INTO roles (codigo, nombre, descripcion, es_asistencial, es_cuenta_tecnica, nivel_jerarquico) VALUES
('medico',       'Médico general (Corte 2)',
 'Atiende, crea pacientes, ejecuta el análisis de IA, aprueba o rechaza reportes y remite a especialista.',
 TRUE,  FALSE, 3),
('especialista', 'Médico especialista (Corte 2)',
 'Recibe remisiones, las acepta y atiende a los pacientes remitidos. Puede aprobar reportes de IA.',
 TRUE,  FALSE, 2),
('contable',     'Contable',
 'Gestiona la facturación de servicios. No ve datos clínicos.',
 FALSE, FALSE, 4)
ON CONFLICT (codigo) DO NOTHING;

-- ---------------------------------------------------------------- permisos
-- medico hereda los permisos clínicos de medico_general, y especialista los
-- de medico_especialista. Se copian en vez de repetirlos a mano para que no
-- se desalineen. Los permisos de los módulos nuevos (IA, remisiones,
-- facturas, alertas) los agrega cada módulo en su propia migración.
--
-- Nota: ninguno de los dos recibe 'auditoria:read' (R03: un médico que pide
-- la auditoría debe recibir 403). contable no recibe ningún permiso clínico.
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT nuevo.id, rp.permiso_id
FROM roles nuevo
JOIN roles base ON base.codigo = 'medico_general'
JOIN roles_permisos rp ON rp.rol_id = base.id
WHERE nuevo.codigo = 'medico'
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT nuevo.id, rp.permiso_id
FROM roles nuevo
JOIN roles base ON base.codigo = 'medico_especialista'
JOIN roles_permisos rp ON rp.rol_id = base.id
WHERE nuevo.codigo = 'especialista'
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

-- admin ya tiene 'usuario:manage' desde 02: con ese permiso crea usuarios y
-- desbloquea cuentas. Se vuelve a asegurar por si la base se creó distinto.
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'admin' AND p.codigo IN ('usuario:manage', 'auditoria:read')
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

-- ---------------------------------------------------------------- cuentas de prueba
-- Una por rol nuevo. Reutilizan el hash Argon2id de la cuenta 'admin' (la
-- contraseña de demostración del equipo), así este archivo nunca contiene
-- una contraseña en claro.
--
-- medico01 y especialista01 quedan ligados a un registro de 'personal' del
-- tipo correspondiente, para que los permisos con alcance 'assigned' y las
-- remisiones tengan un médico real detrás. Comparten ese personal con una
-- cuenta del Corte 1 (medi000X): es solo para la demostración.
-- generar_datos.py inserta usuarios con id explícito, así que la secuencia
-- puede haber quedado atrás y el siguiente INSERT chocaría con una llave
-- existente. Se resincroniza ANTES de crear las cuentas.
SELECT setval(pg_get_serial_sequence('usuarios', 'id'),
              (SELECT COALESCE(MAX(id), 1) FROM usuarios));

INSERT INTO usuarios (username, password_hash, rol_id, personal_id, debe_cambiar_password)
SELECT 'medico01',
       (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'medico'),
       (SELECT p.id FROM personal p WHERE p.tipo_personal = 'medico_general' AND p.activo
         ORDER BY p.id LIMIT 1),
       FALSE
WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE username = 'medico01');

INSERT INTO usuarios (username, password_hash, rol_id, personal_id, debe_cambiar_password)
SELECT 'especialista01',
       (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'especialista'),
       (SELECT p.id FROM personal p WHERE p.tipo_personal = 'medico_especialista' AND p.activo
         ORDER BY p.id LIMIT 1),
       FALSE
WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE username = 'especialista01');

INSERT INTO usuarios (username, password_hash, rol_id, debe_cambiar_password)
SELECT 'contable01',
       (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'contable'),
       FALSE
WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE username = 'contable01');

-- Cuenta para la prueba de bloqueo del tester (R02): así nadie bloquea por
-- accidente una cuenta que se usa en la demostración.
INSERT INTO usuarios (username, password_hash, rol_id, debe_cambiar_password)
SELECT 'bloqueo_prueba',
       (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'medico'),
       FALSE
WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE username = 'bloqueo_prueba');
