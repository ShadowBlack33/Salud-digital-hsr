-- ============================================================================
-- MEJORA 1: causas de cancelación abiertas
-- Las 19 causas específicas (Muñoz-Caicedo et al., 2019) cubren los patrones
-- documentados en la literatura, pero la vida real siempre tiene casos que no
-- encajan en ninguna categoría fija. Se agrega un escape valve por cada
-- responsable, con justificación libre en cancelaciones.detalle (columna
-- que ya existía, ahora se usa también para esto).
-- ============================================================================

-- 'evitable' pasa a admitir NULL: para una causa "Otro" no se puede saber de
-- antemano si es evitable o no — depende del caso específico, que queda
-- descrito en cancelaciones.detalle. NULL = "depende del caso, ver detalle".
ALTER TABLE catalogo_causas_cancelacion ALTER COLUMN evitable DROP NOT NULL;

INSERT INTO catalogo_causas_cancelacion (codigo, descripcion, responsable, origen, evitable)
VALUES
    ('OTRO_PACIENTE',   'Otra causa atribuible al paciente, no listada — ver detalle',   'paciente',   NULL, NULL),
    ('OTRO_PRESTADOR',  'Otra causa atribuible al prestador, no listada — ver detalle',  'prestador',  NULL, NULL),
    ('OTRO_ASEGURADOR', 'Otra causa atribuible al asegurador, no listada — ver detalle', 'asegurador', NULL, NULL)
ON CONFLICT (codigo) DO NOTHING;

-- ============================================================================
-- MEJORA 2: subtipo de la entidad en eventos_estado
-- Hoy entidad_tipo solo dice 'cama' o 'quirofano', sin distinguir UCI de
-- hospitalización general, ni un quirófano cardiovascular de uno estándar.
-- Para saberlo había que cruzar con la tabla camas/quirofanos. Se agrega
-- la columna para que quede visible directamente en la tabla de eventos,
-- que es justo donde se calculan las horas ociosas por tipo de recurso.
-- ============================================================================

ALTER TABLE eventos_estado ADD COLUMN IF NOT EXISTS entidad_subtipo VARCHAR(30);

-- Rellena los eventos de cama ya existentes con su tipo real (UCI, GENERAL, etc.)
UPDATE eventos_estado e
SET entidad_subtipo = tc.codigo
FROM camas c
JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
WHERE e.entidad_tipo = 'cama'
  AND e.entidad_id = c.id
  AND e.entidad_subtipo IS NULL;

-- Rellena los eventos de quirófano según su capacidad real, que es lo que
-- de verdad limita qué cirugías puede recibir ese quirófano
UPDATE eventos_estado e
SET entidad_subtipo = CASE
    WHEN q.tiene_circulacion_extracorporea THEN 'CARDIOVASCULAR'
    WHEN q.tiene_arco_c THEN 'CON_ARCO_C'
    ELSE 'GENERAL'
END
FROM quirofanos q
WHERE e.entidad_tipo = 'quirofano'
  AND e.entidad_id = q.id
  AND e.entidad_subtipo IS NULL;

CREATE INDEX IF NOT EXISTS idx_evt_subtipo ON eventos_estado(entidad_tipo, entidad_subtipo);