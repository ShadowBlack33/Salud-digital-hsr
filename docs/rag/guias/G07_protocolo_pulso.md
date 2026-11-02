---
id: G07
titulo: Protocolo interno de Pulso para alertas críticas, reportes de IA y remisiones
fuente: Equipo Pulso (Universidad Autónoma de Occidente). Documentación del proyecto: ml/UMBRAL.md, docs/EVENTOS.md y docs/NORMATIVA.md, 2026.
url: https://github.com/ShadowBlack33/Salud-digital-hsr
tipo: guia
audiencia: operativa
---

# Protocolo interno de Pulso para alertas críticas, reportes de IA y remisiones

Documento interno del Hospital San Rafael (caso hipotético), escrito por el equipo de Pulso a partir de la documentación del proyecto.

## Modelo de riesgo de UCI

El modelo vitaldb-1 es una regresión logística entrenada con cirugías reales de adultos de la base VitalDB. Estima la probabilidad de que un paciente quirúrgico pase al menos un día en UCI después de la cirugía. Usa cinco variables: edad, sexo, glucosa, potasio y hemoglobina. Si no llega al menos uno de los tres laboratorios, el modelo no predice.

## Umbral de alerta

El umbral es 0,40. Se eligió entre los umbrales con sensibilidad de al menos 0,80 el de mayor especificidad. En el conjunto de prueba de 1.596 cirugías tiene sensibilidad 0,80, especificidad 0,47, valor predictivo positivo 0,24 y AUC 0,71. Con este umbral el modelo avisa de 221 de los 276 pacientes que sí necesitaron UCI; con 0,50 se escaparían 100 en lugar de 55.

## Reporte de IA

El reporte de IA nace pendiente y no entra a la historia clínica. Un médico o especialista lo revisa y lo aprueba o lo rechaza con una observación. Solo el reporte aprobado entra a la historia. El rechazado no se borra: queda como evidencia en la base y en la auditoría.

## Alerta crítica y escalamiento

Si la probabilidad supera el umbral, se crea una alerta crítica para el clínico que pidió el análisis. La alerta sigue activa hasta que un médico o especialista la reconoce escribiendo la conducta tomada. Si nadie la reconoce en 5 minutos, escala a los otros médicos y especialistas a cargo del paciente, que son quienes pueden resolverla; no se escala al administrador. El coordinador del hospital ve un contador de alertas sin atender por médico, sin datos del paciente, para saber quién tiene alertas pendientes y desde hace cuánto.

## Remisiones

El médico remite a una especialidad indicando para qué necesita al especialista (valoración, diagnóstico, tratamiento, procedimiento o seguimiento), el motivo y la prioridad: rutinaria, prioritaria o urgente. El sistema asigna el especialista de esa especialidad con menos remisiones abiertas, para repartir la carga. El especialista no puede rechazar la remisión: si el médico la pidió es porque el paciente la necesita. La acepta y, cuando atiende al paciente, la cierra como atendida. Un paciente puede tener varios especialistas a la vez.

## Factura automática

Cuando un clínico aprueba un reporte de IA, se crea una factura en MongoDB ligada al reporte. Aprobar dos veces no duplica el cobro.

## Sesgo conocido del modelo

El modelo detecta el 58,5 % de las mujeres que terminan en UCI frente al 91,2 % de los hombres, y en mayores de 65 años tiene especificidad de 0,073. El siguiente paso es un umbral por subgrupo o agregar el ASA.
