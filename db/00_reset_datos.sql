-- Borra solo los datos generados y de uso (personal, usuarios, pacientes,
-- encuentros, reportes de IA, remisiones, auditoría, etc.), SIN tocar roles,
-- permisos ni catálogos clínicos, ni las guías indexadas del RAG.
-- Se usa para regenerar los datos sintéticos desde cero:
--   python scripts/aplicar_sql.py db/00_reset_datos.sql
--   python scripts/generar_datos.py
--   python scripts/aplicar_sql.py db/01_datos_sinteticos.sql
BEGIN;

TRUNCATE
    personal, usuarios, quirofanos, camas, pacientes, encuentros,
    observaciones, cancelaciones, eventos_estado, sesiones,
    historial_cambios, agenda_consulta_externa, alertas, predicciones,
    log_auditoria, reportes_ia, remisiones, traslados, turnos_area,
    notificaciones, eventos_fhir, rag_consultas
RESTART IDENTITY CASCADE;

-- Del índice del RAG solo se borran las historias (las guías se conservan).
DELETE FROM rag_fragmentos WHERE tipo = 'historia';

COMMIT;
