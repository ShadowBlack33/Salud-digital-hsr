-- ============================================================================
-- 11 · Quitar el perfil de ingeniería biomédica (decisión del equipo)
--
-- Se probó un perfil "ingeniero_biomedico" y se descartó: nadie en la
-- operación del hospital simulado registra fallas de equipos, así que el
-- perfil no tenía flujo real. Este script deshace lo que haya quedado de él
-- en la base (rol, cuenta biomedico01, permisos equipo:*, tabla
-- fuera_servicio). Es seguro correrlo aunque nunca se haya creado.
--   python scripts/aplicar_sql.py db/11_quitar_biomedico.sql
-- ============================================================================
BEGIN;
UPDATE sesiones SET revocado_at = NOW()
 WHERE revocado_at IS NULL AND usuario_id IN (SELECT id FROM usuarios WHERE username = 'biomedico01');
-- La cuenta se desactiva (no se borra: la auditoría la referencia).
UPDATE usuarios SET activo = FALSE WHERE username = 'biomedico01';
DELETE FROM roles_permisos WHERE rol_id IN (SELECT id FROM roles WHERE codigo = 'ingeniero_biomedico')
   OR permiso_id IN (SELECT id FROM permisos WHERE recurso = 'equipo');
DELETE FROM permisos WHERE recurso = 'equipo';
DROP TABLE IF EXISTS fuera_servicio;
COMMIT;
