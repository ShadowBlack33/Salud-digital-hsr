---
id: G10
titulo: Escala NEWS2 de alerta temprana
fuente: Royal College of Physicians. National Early Warning Score (NEWS) 2: Standardising the assessment of acute-illness severity in the NHS. Informe actualizado del grupo de trabajo. Londres: RCP, 2017.
url: https://www.rcp.ac.uk/improving-care/resources/national-early-warning-score-news-2/
tipo: guia
audiencia: clinica
---

# Escala NEWS2 de alerta temprana

Resumen del equipo de Pulso de la escala NEWS2 del Royal College of Physicians (2017), que estandariza cómo se detecta el deterioro de un adulto hospitalizado a partir de sus signos vitales.

## Qué mide

NEWS2 suma puntos de seis parámetros fisiológicos: frecuencia respiratoria, saturación de oxígeno, presión arterial sistólica, frecuencia cardiaca (pulso), nivel de conciencia y temperatura. Cada parámetro da de 0 a 3 puntos y, si el paciente recibe oxígeno suplementario, se suman 2 puntos más. El nivel de conciencia se valora con ACVPU: alerta, confusión nueva, respuesta a la voz, respuesta al dolor o sin respuesta; cualquier estado distinto de alerta, incluida la confusión nueva, da 3 puntos.

<!-- preguntas
¿Qué datos de los signos vitales del enfermo debo sumar para sacar la puntuación del test?
¿Cuáles son los seis signos corporales que evalúa esta tabla y cuántos puntos da cada uno?
¿Cómo se califica si el enfermo está desorientado y cuántos puntos vale darle oxígeno extra?
¿Qué aspectos de la condición física del internado se revisan para calcular el total de puntos?
-->

## Valores que dan 3 puntos

Dan la puntuación máxima de 3 en un solo parámetro: frecuencia respiratoria de 8 o menos o de 25 o más por minuto; saturación de oxígeno de 91 % o menos en la escala 1; presión sistólica de 90 mmHg o menos o de 220 o más; pulso de 40 o menos o de 131 o más por minuto; cualquier estado de conciencia distinto de alerta; y temperatura de 35,0 °C o menos. Los rangos de 1 y 2 puntos están en la tabla oficial del RCP y deben consultarse allí.

<!-- preguntas
¿Qué cifra exacta de la presión o del aire en la sangre dispara la máxima calificación de golpe?
¿Cuáles son los límites extremos en la respiración o en el pulso que marcan tres unidades de una vez?
¿En qué momento exacto se le asigna la peor nota a un solo signo vital del paciente encamado?
¿Qué rangos críticos en la temperatura o en el ritmo cardíaco equivalen a la puntuación más alta posible?
-->

## Escalas de saturación

La escala 1 es la de uso general, con meta de 94 a 98 %. La escala 2, con meta de 88 a 92 %, es solo para pacientes con insuficiencia respiratoria hipercápnica confirmada y la decide un clínico competente.

<!-- preguntas
¿Cuándo se debe usar la tabla especial para el nivel de oxígeno en pacientes con EPOC o retención de aire?
¿Cuál es la diferencia entre la primera y la segunda tabla para medir el oxígeno en la sangre?
¿A qué meta de oxígeno debo apuntar si el enfermo tiene una falla respiratoria donde acumula mucho gas carbónico?
¿Quién es el encargado de ordenar el uso del segundo rango de oxigenometría en el piso?
-->

## Umbrales y respuesta clínica

Puntaje total 0: monitoreo mínimo cada 12 horas. Puntaje de 1 a 4 (riesgo bajo): valoración por enfermería, que decide si cambia la frecuencia de monitoreo; monitoreo cada 4 a 6 horas. Un solo parámetro con 3 puntos (puntaje rojo): revisión urgente por un médico de la sala y monitoreo al menos cada hora. Puntaje de 5 a 6 (riesgo medio): umbral clave para revisión urgente por un clínico con competencia en paciente agudo, que decide si escala a cuidado crítico; monitoreo al menos cada hora. Puntaje de 7 o más (riesgo alto): respuesta de emergencia por un equipo con competencias de cuidado crítico, usualmente traslado a un área de mayor complejidad y monitoreo continuo.

<!-- preguntas
¿Cada cuánto debo ir a revisar a un enfermo que sacó cinco puntos en el test de alerta?
¿A qué especialista debo llamar de urgencia si un solo parámetro del monitor marca tres puntos rojos?
¿Qué equipo médico debe venir corriendo a auxiliar al paciente cuando la suma total pasa de seis?
¿Cuál es la frecuencia con la que se deben tomar los signos si el puntaje total dio cero?
-->

## Advertencias

La preocupación clínica del equipo prevalece sobre el puntaje: si el clínico cree que hay que escalar, se escala aunque el puntaje sea bajo. Con sospecha de infección y un puntaje de 5 o más hay que pensar en sepsis. NEWS2 no se usa en menores de 16 años ni en embarazadas, y puede ser poco confiable en lesión medular.

<!-- preguntas
¿A qué pacientes menores de edad o gestantes no se les puede aplicar esta escala de deterioro?
¿Qué pasa si a mí como doctor me parece que el enfermo está grave aunque la calculadora diga lo contrario?
¿En qué tipo de pacientes con daño en la columna vertebral este puntaje puede fallar o no ser tan exacto?
¿Cuándo debo sospechar que hay una infección grave o sepsis mirando el resultado del test?
-->

## Relación con Pulso

Pulso recibe signos vitales y laboratorios como observaciones (también desde laboratorios externos por FHIR) y marca valores críticos. NEWS2 es el criterio que un clínico usaría para decidir si un paciente de piso necesita valoración por UCI, que es justo la capacidad que Pulso vigila.

<!-- preguntas
¿De qué manera la plataforma Pulso se conecta con esta escala para avisar si alguien se va a complicar?
¿Cómo usa el sistema Pulso los resultados de este test para decidir si hay que mandar al enfermo a cuidados intensivos?
¿Qué datos externos jala la aplicación Pulso para mostrar las alertas críticas de los internados?
¿Por qué es importante meter los puntos del NEWS2 en la herramienta Pulso para vigilar el piso?
-->
