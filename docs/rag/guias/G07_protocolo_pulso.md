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

<!-- preguntas
¿Cuáles son los datos exactos que necesita el sistema para calcular si alguien va para cuidados intensivos?
¿Qué pasa si a mi paciente le falta un examen de sangre y quiero calcular su riesgo postoperatorio?
¿De dónde sacaron los datos para armar la fórmula que predice complicaciones después de operar?
¿Cómo sabe el algoritmo si una persona recién operada va a requerir cama en cuidados intensivos?
-->

## Umbral de alerta

El umbral es 0,40. Se eligió entre los umbrales con sensibilidad de al menos 0,80 el de mayor especificidad. En el conjunto de prueba de 1.596 cirugías tiene sensibilidad 0,80, especificidad 0,47, valor predictivo positivo 0,24 y AUC 0,71. Con este umbral el modelo avisa de 221 de los 276 pacientes que sí necesitaron UCI; con 0,50 se escaparían 100 en lugar de 55.

<!-- preguntas
¿A partir de qué puntaje exacto el sistema empieza a lanzar avisos de peligro para los recién operados?
¿Por qué se escogió ese número y no otro más alto para avisar sobre camas de cuidados intensivos?
¿Cuántos pacientes que sí terminaron gravemente enfermos se le escapan al programa con la configuración actual?
¿Qué tan confiable es el porcentaje que usa la plataforma para advertir sobre ingresos a cuidados intensivos?
-->

## Reporte de IA

El reporte de IA nace pendiente y no entra a la historia clínica. Un médico o especialista lo revisa y lo aprueba o lo rechaza con una observación. Solo el reporte aprobado entra a la historia. El rechazado no se borra: queda como evidencia en la base y en la auditoría.

<!-- preguntas
¿Dónde queda guardado el concepto del computador cuando un galeno decide que no sirve para el enfermo?
¿El diagnóstico que bota el computador se va de una vez para la carpeta oficial del paciente?
¿Quién tiene que dar el visto bueno para que el concepto del computador pase a la historia clínica?
¿Qué ocurre con el papelito que genera el software si un especialista decide que no está de acuerdo?
-->

## Alerta crítica y escalamiento

Si la probabilidad supera el umbral, se crea una alerta crítica para el clínico que pidió el análisis. La alerta sigue activa hasta que un médico o especialista la reconoce escribiendo la conducta tomada. Si nadie la reconoce en 5 minutos, escala a los otros médicos y especialistas a cargo del paciente, que son quienes pueden resolverla; no se escala al administrador. El coordinador del hospital ve un contador de alertas sin atender por médico, sin datos del paciente, para saber quién tiene alertas pendientes y desde hace cuánto.

<!-- preguntas
¿A quién le suena el aviso urgente si el doctor de cabecera no mira la pantalla a tiempo?
¿Cómo hace el jefe del centro médico para enterarse qué doctor tiene avisos sin revisar y hace cuánto?
¿Qué debe hacer el galeno para que el aviso de peligro en la pantalla deje de sonar?
¿A qué personas les llega el campanazo cuando el médico principal se demoró en responder el aviso?
-->

## Remisiones

El médico remite a una especialidad indicando para qué necesita al especialista (valoración, diagnóstico, tratamiento, procedimiento o seguimiento), el motivo y la prioridad: rutinaria, prioritaria o urgente. El sistema asigna el especialista de esa especialidad con menos remisiones abiertas, para repartir la carga. El especialista no puede rechazar la remisión: si el médico la pidió es porque el paciente la necesita. La acepta y, cuando atiende al paciente, la cierra como atendida. Un paciente puede tener varios especialistas a la vez.

<!-- preguntas
¿Cómo hace el programa para repartir los casos nuevos entre los diferentes especialistas sin sobrecargar a nadie?
¿Puede un especialista negarse a atender un caso que le mandaron desde urgencias o consulta externa?
¿Qué datos debo llenar en el sistema cuando necesito mandar a un enfermo con el cardiología u otra subespecialidad?
¿Un paciente puede ser tratado por varios médicos especialistas al mismo tiempo dentro de la institución?
-->

## Factura automática

Cuando un clínico aprueba un reporte de IA, se crea una factura en MongoDB ligada al reporte. Aprobar dos veces no duplica el cobro.

<!-- preguntas
Si le doy clic dos veces al botón de aceptar el concepto, ¿le vamos a cobrar doble al enfermo?
¿En qué momento exacto se genera el cobro en el sistema informático tras una evaluación médica?
¿Dónde queda registrada la cuenta de cobro que genera el sistema cuando un galeno valida un concepto?
¿Qué base de datos guarda el cobro que se genera automáticamente al aceptar el análisis del computador?
-->

## Sesgo conocido del modelo

El modelo detecta el 58,5 % de las mujeres que terminan en UCI frente al 91,2 % de los hombres, y en mayores de 65 años tiene especificidad de 0,073. El siguiente paso es un umbral por subgrupo o agregar el ASA.

<!-- preguntas
¿Es verdad que el sistema funciona peor cuando se trata de evaluar a las señoras mayores de edad?
¿Qué fallas tiene la aplicación para detectar complicaciones en las mujeres en comparación con los varones?
¿Por qué el programa acierta mucho menos cuando los pacientes que están en recuperación son abuelitos?
¿Qué piensan hacer los ingenieros para corregir las fallas que tiene el algoritmo con ciertos grupos de pacientes?
-->
