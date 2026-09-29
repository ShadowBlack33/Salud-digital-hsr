-- Agrega los permisos de imágenes médicas (PACS) sobre una base que YA tiene
-- todo lo demás cargado. A diferencia de 02_seed_catalogos.sql (que recrea
-- el catálogo entero desde cero), este archivo es seguro de correr sobre
-- una base compartida en uso: no toca roles, permisos ni asignaciones que
-- ya existan, y se puede correr más de una vez sin duplicar nada.

INSERT INTO permisos (codigo, recurso, accion, alcance, descripcion) VALUES
('imagen:create:all',  'imagen','create','all','Subir una imagen al PACS'),
('imagen:read:all',    'imagen','read','all','Ver imágenes de cualquier paciente'),
('imagen:read:self',   'imagen','read','self','Ver sus propias imágenes'),
('imagen:delete:all',  'imagen','delete','all','Eliminar una imagen del PACS (solo admin, a propósito)')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE (r.codigo, p.codigo) IN (
    ('director_medico',        'imagen:read:all'),
    ('coordinador_quirurgico', 'imagen:read:all'),
    ('medico_especialista',    'imagen:create:all'),
    ('medico_especialista',    'imagen:read:all'),
    ('medico_general',         'imagen:create:all'),
    ('medico_general',         'imagen:read:all'),
    ('anestesiologo',          'imagen:create:all'),
    ('anestesiologo',          'imagen:read:all'),
    ('enfermero_jefe',         'imagen:create:all'),
    ('enfermero_jefe',         'imagen:read:all'),
    ('enfermero',              'imagen:create:all'),
    ('enfermero',              'imagen:read:all'),
    ('auxiliar_enfermeria',    'imagen:create:all'),
    ('auxiliar_enfermeria',    'imagen:read:all'),
    ('paciente',               'imagen:read:self')
)
ON CONFLICT (rol_id, permiso_id) DO NOTHING;

-- admin: el CROSS JOIN que le da "todos los permisos" corrió una sola vez,
-- hace tiempo -- no se actualiza solo cuando aparecen permisos nuevos.
-- Hay que dárselos explícitamente también.
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'admin' AND p.recurso = 'imagen'
ON CONFLICT (rol_id, permiso_id) DO NOTHING;
