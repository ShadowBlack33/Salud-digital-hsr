-- ============================================================================
-- 12 · Turnos de los enfermeros(as) jefe por área
--
-- Siempre hay un jefe de turno en cada área con camas. Esquema de la
-- demostración (como en hospitales de alta complejidad de Cali): mañana 07-13
-- (6 h), tarde 13-19 (6 h) y noche 19-07 (12 h). Tres jefes por área rotan:
-- el que hoy hace la mañana, mañana hace la tarde, y así.
--
-- Solo el jefe de turno opera su área (asignar camas, cambiar estados,
-- traslados); los demás jefes del área la ven en solo lectura. Si el de turno
-- falta, otro jefe del área puede "cubrir el turno" (queda auditado).
--
-- Cuentas (clave de demostración): jefe_urg, jefe_urg2, jefe_urg3, y lo mismo
-- para uci, ucip, piso4 y piso5. Se puede correr más de una vez: regenera la
-- programación desde ayer hasta dentro de 14 días sin tocar las coberturas.
--   python scripts/aplicar_sql.py db/12_turnos.sql
-- ============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS turnos_area (
    id           SERIAL PRIMARY KEY,
    servicio_id  INT NOT NULL REFERENCES servicios(id),
    usuario_id   INT NOT NULL REFERENCES usuarios(id),
    inicio       TIMESTAMPTZ NOT NULL,
    fin          TIMESTAMPTZ NOT NULL,
    tipo         VARCHAR(12) NOT NULL CHECK (tipo IN ('manana', 'tarde', 'noche', 'cobertura')),
    motivo       TEXT,
    created_by   INT REFERENCES usuarios(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (fin > inicio)
);
CREATE INDEX IF NOT EXISTS idx_turnos_area_tiempo ON turnos_area (servicio_id, inicio, fin);

-- Tres jefes por área (el primero ya existe desde la migración 11).
SELECT setval(pg_get_serial_sequence('usuarios', 'id'), (SELECT COALESCE(MAX(id), 1) FROM usuarios));
INSERT INTO usuarios (username, password_hash, rol_id, personal_id, servicio_id, debe_cambiar_password)
SELECT v.base || v.n, (SELECT password_hash FROM usuarios WHERE username = 'admin'),
       (SELECT id FROM roles WHERE codigo = 'enfermero_jefe'), NULL,
       (SELECT id FROM servicios WHERE codigo = v.servicio), FALSE
FROM (VALUES ('jefe_urg', 'URG'), ('jefe_uci', 'UCI_ADU'), ('jefe_ucip', 'UCI_PED'),
             ('jefe_piso4', 'HOSP_1'), ('jefe_piso5', 'HOSP_2')) AS a(base, servicio)
CROSS JOIN (VALUES ('2'), ('3')) AS n(n)
CROSS JOIN LATERAL (SELECT a.base, n.n, a.servicio) AS v
WHERE NOT EXISTS (SELECT 1 FROM usuarios u WHERE u.username = v.base || v.n);

-- Programación: borra lo programado (no las coberturas) y la regenera.
DELETE FROM turnos_area WHERE tipo <> 'cobertura' AND fin > (CURRENT_DATE - 1);
WITH jefes AS (
    SELECT s.id AS servicio_id, u.id AS usuario_id,
           ROW_NUMBER() OVER (PARTITION BY s.id ORDER BY u.username) - 1 AS k
    FROM servicios s
    JOIN usuarios u ON u.servicio_id = s.id AND u.activo
    JOIN roles r ON r.id = u.rol_id AND r.codigo = 'enfermero_jefe'
    WHERE s.codigo IN ('URG', 'UCI_ADU', 'UCI_PED', 'HOSP_1', 'HOSP_2')
),
cuantos AS (SELECT servicio_id, COUNT(*) AS n FROM jefes GROUP BY servicio_id),
dias AS (SELECT d::date AS dia, ROW_NUMBER() OVER (ORDER BY d) AS i
         FROM generate_series(CURRENT_DATE - 1, CURRENT_DATE + 14, INTERVAL '1 day') AS d),
franjas AS (SELECT * FROM (VALUES (0, 'manana', '07:00'::time, INTERVAL '6 hours'),
                                  (1, 'tarde',  '13:00'::time, INTERVAL '6 hours'),
                                  (2, 'noche',  '19:00'::time, INTERVAL '12 hours')) AS f(s, tipo, hora, dur))
INSERT INTO turnos_area (servicio_id, usuario_id, inicio, fin, tipo)
SELECT j.servicio_id, j.usuario_id,
       (d.dia + f.hora) AT TIME ZONE 'America/Bogota',
       (d.dia + f.hora + f.dur) AT TIME ZONE 'America/Bogota',
       f.tipo
FROM dias d CROSS JOIN franjas f
JOIN cuantos c ON TRUE
JOIN jefes j ON j.servicio_id = c.servicio_id AND j.k = (d.i + f.s) % c.n;

COMMIT;
