-- Corrige tipo_documento en los pacientes que ya existen, para que sea
-- consistente con su fecha de nacimiento (antes se asignaba al azar, sin
-- mirar la edad -- por eso salían TI de gente nacida en los 60).
-- No toca nada cifrado, no necesita las claves de la aplicación.
-- Seguro de correr más de una vez.

UPDATE pacientes SET tipo_documento = CASE
    WHEN fecha_nacimiento > CURRENT_DATE - INTERVAL '7 years'  THEN 'RC'
    WHEN fecha_nacimiento > CURRENT_DATE - INTERVAL '18 years' THEN 'TI'
    -- Si ya es CC o CE (documento de adulto) y de verdad es adulto, se deja igual.
    -- Si tenía un documento de menor (RC/TI) pero en realidad es adulto,
    -- se corrige a CC.
    WHEN tipo_documento IN ('RC', 'TI') THEN 'CC'
    ELSE tipo_documento
END
WHERE activo;
