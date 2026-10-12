-- ============================================================================
-- 09 · Perfiles definitivos: sin roles duplicados y cada uno con su trabajo
--
-- El Corte 2 exige los códigos admin, medico, especialista, paciente y
-- contable. En 08 se agregaron al lado de los del Corte 1, y quedaron
-- duplicados (dos "médico general", dos "médico especialista", dos de
-- facturación). Este archivo los fusiona y redefine dos perfiles:
--
--   medico_general       -> medico         (sus cuentas pasan al código nuevo)
--   medico_especialista  -> especialista
--   facturacion          -> contable
--   director_medico      -> coordinador    "Coordinador del hospital": mira
--                           el hospital entero (capacidad, riesgo de colapso,
--                           dinero, IA). No ve pacientes uno por uno.
--   coordinador_quirurgico -> enfermero_jefe, que pasa a hacer la
--                           coordinación quirúrgica: programa y reprograma
--                           cirugías, mueve una programada por una urgencia.
--
-- Además, medico y especialista ven SOLO sus pacientes (alcance 'assigned'):
-- los que registraron, los que tienen un encuentro a su cargo y, cuando
-- exista el módulo, los remitidos que aceptaron.
--
-- Se puede correr más de una vez. Todo va en una transacción.
--
-- Uso (solo Carlos sobre la base compartida):
--   python scripts/aplicar_sql.py db/09_perfiles.sql
-- ============================================================================
BEGIN;

-- --------------------------------------------------------- nombres claros
UPDATE roles SET nombre = 'Médico general',
       descripcion = 'Atiende consulta y urgencias. Ve solo sus pacientes: registra, ejecuta el análisis de IA, lo aprueba o rechaza y remite al especialista.'
 WHERE codigo = 'medico';
UPDATE roles SET nombre = 'Médico especialista',
       descripcion = 'Recibe remisiones y atiende a sus pacientes. Ve si un paciente suyo está en cirugía y si él está asignado. Puede aprobar reportes de IA.'
 WHERE codigo = 'especialista';
UPDATE roles SET nombre = 'Contable / facturación',
       descripcion = 'Gestiona la facturación de servicios (particular y EPS), pagos y anulaciones. No ve datos clínicos.'
 WHERE codigo = 'contable';

-- --------------------------------------------- director_medico -> coordinador
UPDATE roles SET codigo = 'coordinador'
 WHERE codigo = 'director_medico'
   AND NOT EXISTS (SELECT 1 FROM roles WHERE codigo = 'coordinador');
INSERT INTO roles (codigo, nombre, descripcion, es_asistencial, es_cuenta_tecnica, nivel_jerarquico)
SELECT 'coordinador', '', '', FALSE, FALSE, 1
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE codigo = 'coordinador');
UPDATE roles SET nombre = 'Coordinador del hospital',
       descripcion = 'Supervisa el hospital completo: capacidad por área, riesgo de colapso, ingresos y pérdidas, desempeño de la IA. No opera ni consulta pacientes individuales.',
       es_asistencial = FALSE, nivel_jerarquico = 1
 WHERE codigo = 'coordinador';

UPDATE roles SET nombre = 'Enfermero(a) jefe',
       descripcion = 'Coordina el servicio y la programación quirúrgica: programa, reprograma y mueve cirugías ante una urgencia; gestiona camas y quirófanos.'
 WHERE codigo = 'enfermero_jefe';

-- ------------------------------------------------- mover cuentas y borrar duplicados
-- La cuenta de demostración 'coordinador' pasa a ser el coordinador del
-- hospital; el resto de coordinadores quirúrgicos, a enfermero jefe.
UPDATE usuarios SET rol_id = (SELECT id FROM roles WHERE codigo = 'coordinador')
 WHERE username = 'coordinador';

UPDATE usuarios u SET rol_id = nuevo.id
  FROM roles viejo, roles nuevo
 WHERE u.rol_id = viejo.id
   AND (viejo.codigo, nuevo.codigo) IN (
        ('medico_general', 'medico'),
        ('medico_especialista', 'especialista'),
        ('facturacion', 'contable'),
        ('coordinador_quirurgico', 'enfermero_jefe'));

-- Las alertas dirigidas a un rol viejo se reasignan antes de borrarlo.
UPDATE alertas a SET dirigida_a_rol = nuevo.id
  FROM roles viejo, roles nuevo
 WHERE a.dirigida_a_rol = viejo.id
   AND (viejo.codigo, nuevo.codigo) IN (
        ('medico_general', 'medico'),
        ('medico_especialista', 'especialista'),
        ('facturacion', 'contable'),
        ('coordinador_quirurgico', 'enfermero_jefe'));

DELETE FROM roles_permisos WHERE rol_id IN (SELECT id FROM roles WHERE codigo IN
       ('medico_general', 'medico_especialista', 'facturacion', 'coordinador_quirurgico'));
DELETE FROM roles WHERE codigo IN
       ('medico_general', 'medico_especialista', 'facturacion', 'coordinador_quirurgico');

-- ----------------------------------------------------------- permisos
-- Función auxiliar: deja a un rol EXACTAMENTE con la lista dada.
CREATE OR REPLACE FUNCTION pg_temp.fijar_permisos(p_rol TEXT, p_codigos TEXT[]) RETURNS VOID AS $$
BEGIN
    DELETE FROM roles_permisos
     WHERE rol_id = (SELECT id FROM roles WHERE codigo = p_rol);
    INSERT INTO roles_permisos (rol_id, permiso_id)
    SELECT r.id, p.id FROM roles r, permisos p
     WHERE r.codigo = p_rol AND p.codigo = ANY(p_codigos)
    ON CONFLICT (rol_id, permiso_id) DO NOTHING;
END $$ LANGUAGE plpgsql;

-- Los módulos del Corte 2 (IA, remisiones, alertas, facturas) agregan sus
-- propios permisos en sus migraciones: se conservan los que ya existan.
CREATE TEMP TABLE _corte2 ON COMMIT DROP AS
SELECT r.codigo AS rol, p.codigo AS permiso
  FROM roles_permisos rp JOIN roles r ON r.id = rp.rol_id JOIN permisos p ON p.id = rp.permiso_id
 WHERE p.recurso NOT IN ('paciente','encuentro','observacion','imagen','cama','quirofano',
                         'agenda','fhir','usuario','auditoria','analitica','facturacion');

SELECT pg_temp.fijar_permisos('medico', ARRAY[
    'paciente:create:all','paciente:read:assigned','paciente:update:own',
    'encuentro:create:all','encuentro:read:assigned','encuentro:update:own','encuentro:delete:own',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'imagen:create:all','imagen:read:all','fhir:read:all']);

SELECT pg_temp.fijar_permisos('especialista', ARRAY[
    'paciente:create:all','paciente:read:assigned','paciente:update:own','paciente:delete:own',
    'encuentro:create:all','encuentro:read:assigned','encuentro:update:own','encuentro:delete:own',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'imagen:create:all','imagen:read:all','quirofano:read:all','fhir:read:all']);

SELECT pg_temp.fijar_permisos('contable', ARRAY['facturacion:read','analitica:read']);

SELECT pg_temp.fijar_permisos('coordinador', ARRAY[
    'analitica:read','facturacion:read','cama:read:all','quirofano:read:all','agenda:read:all']);

SELECT pg_temp.fijar_permisos('enfermero_jefe', ARRAY[
    'paciente:read:all',
    'encuentro:create:all','encuentro:read:all','encuentro:update:all','encuentro:delete:own',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'imagen:create:all','imagen:read:all',
    'cama:read:all','cama:update:all','quirofano:read:all','quirofano:update:all',
    'agenda:create:all','agenda:read:all','agenda:update:all','agenda:priorizar',
    'analitica:read','fhir:read:all']);

INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM _corte2 c JOIN roles r ON r.codigo = c.rol JOIN permisos p ON p.codigo = c.permiso
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

-- ----------------------------------------------------------- cuenta de demo
-- Enfermera jefe para la coordinación quirúrgica, ligada a un registro de
-- personal real (mismo hash que 'admin': la clave de demostración).
SELECT setval(pg_get_serial_sequence('usuarios', 'id'), (SELECT COALESCE(MAX(id), 1) FROM usuarios));
INSERT INTO usuarios (username, password_hash, rol_id, personal_id, debe_cambiar_password)
SELECT 'jefe01',
       (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'enfermero_jefe'),
       (SELECT p.id FROM personal p WHERE p.tipo_personal = 'enfermero_jefe' AND p.activo ORDER BY p.id LIMIT 1),
       FALSE
WHERE NOT EXISTS (SELECT 1 FROM usuarios WHERE username = 'jefe01');

-- Las sesiones abiertas llevan los permisos viejos dentro del token: se
-- revocan para que todos entren con su perfil nuevo.
UPDATE sesiones SET revocado_at = NOW() WHERE revocado_at IS NULL;

COMMIT;
