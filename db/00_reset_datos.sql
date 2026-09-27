-- Borra solo los datos generados (personal, pacientes, encuentros, etc.),
-- SIN tocar roles, permisos ni catálogos clínicos (esos ya están bien).
-- Se usa cuando hay que regenerar los datos sintéticos desde cero.

TRUNCATE
    personal, usuarios, quirofanos, camas, pacientes, encuentros,
    observaciones, cancelaciones, eventos_estado, sesiones,
    historial_cambios, agenda_consulta_externa, alertas, predicciones,
    log_auditoria
RESTART IDENTITY CASCADE;
