---
id: G08
titulo: Facturación de servicios en Pulso
fuente: Equipo Pulso (Universidad Autónoma de Occidente). Documentación del proyecto: docs/CONTABILIDAD.md y docs/CONTRATO_FACTURACION.md, 2026.
url: https://github.com/ShadowBlack33/Salud-digital-hsr
tipo: guia
audiencia: facturacion
---

# Facturación de servicios en Pulso

Guía interna para el perfil contable del Hospital San Rafael (caso hipotético), escrita por el equipo de Pulso a partir de la documentación del módulo de contabilidad.

## Qué es una factura en Pulso

Cada cobro es una factura con un identificador legible del tipo F-250001. Es una referencia interna de cobro: no es una factura electrónica de la DIAN ni un reporte RIPS, no tiene validez fiscal y no se envía a ninguna entidad. Sirve para llevar el control de cuánto se cobra por cada servicio y quién lo paga.

<!-- preguntas
¿Ese papel que generamos acá sirve para mandárselo a la DIAN o pa' la contabilidad?
¿Para qué sirve el número ese que empieza por efe si eso no es un documento legal?
¿Cómo llevamos el control interno de lo que cobra la clínica por cada procedimiento?
¿Ese registro de cobro interno tiene alguna validez ante la DIAN o los RIPS?
-->

## Estados de una factura

Una factura nace pendiente. Puede pasar a radicada cuando se presenta a la entidad, a glosada si la entidad la objeta y a pagada cuando se recibe el pago; se puede marcar como pagada desde pendiente, radicada o glosada. También se puede anular con un motivo de al menos 5 caracteres. Una factura pagada no se puede anular: no existe nota crédito.

<!-- preguntas
¿En qué momento puedo echar para atrás un cobro que ya tiene el dinero en la caja?
¿Qué pasa cuando la entidad promotora de salud nos objeta un cobro que le pasamos?
¿Cuál es el caminito que recorre un cobro desde que nace hasta que entra la plata?
¿Cuántas letras mínimas me pide el sistema para echar para atrás un cobro errado?
-->

## Tipos de cobro

Los tipos de cobro son consulta, urgencias, hospitalización, cirugía, imagenología, laboratorio, medicamentos, insumos, terapia, análisis de IA, remisión y otros. El tarifario tiene 40 servicios con su código y su valor de referencia.

<!-- preguntas
¿Dónde veo el listado con los códigos y precios de referencia de los cuarenta servicios habilitados?
¿Cuáles son las categorías en las que podemos clasificar los cobros por la atención dada?
¿Qué clasificaciones tenemos disponibles para los servicios prestados a los enfermos en la institución?
¿En qué grupo metemos los procedimientos de imágenes, laboratorios o cirugías que realizamos acá?
-->

## Quién paga: cobertura y reparto del valor

La cobertura puede ser particular, EPS, régimen especial, SOAT o medicina prepagada. Un paciente particular paga todo. Con SOAT o régimen especial el paciente paga 0. Con prepagada paga el menor valor entre el servicio y 35.000 pesos. En consulta y urgencias con EPS paga la cuota moderadora: Pulso usa como referencia interna 4.700 pesos en el régimen contributivo (el valor de 2025 del rango de menos de 2 salarios mínimos) y 0 en el subsidiado. En los demás servicios con EPS paga un copago del 11,5 % en el contributivo y del 10 % en el subsidiado; el resto lo paga la entidad. Los valores oficiales vigentes, por rango de ingreso y con sus topes, están en la guía de cuotas moderadoras y copagos.

<!-- preguntas
¿Cuánto le toca poner de su bolsillo a un enfermo que viene por medicina prepagada?
¿Cómo se reparte el pago entre el usuario y la entidad cuando es un caso de SOAT?
¿Qué porcentaje le cobramos de copago a un afiliado al régimen subsidiado en hospitalización?
¿A cuánto asciende la cuota moderadora que le cobramos a alguien del contributivo en urgencias?
-->

## Factura automática del análisis de IA

Cuando un médico aprueba un reporte de IA, se crea sola una factura del análisis (código IA0001) ligada a ese reporte. Un reporte solo puede tener una factura: si la aprobación llega dos veces, se devuelve la factura que ya existía y no se cobra doble. Un reporte rechazado no se factura.

<!-- preguntas
¿Qué pasa si el galeno aprueba dos veces el mismo reporte de inteligencia artificial?
¿Cómo se genera el cobro cuando el doctor le da el visto bueno a un examen de IA?
¿Le cobramos algo al enfermo si el médico rechaza el reporte que hizo la inteligencia artificial?
¿El sistema evita que le cobremos doble al usuario si el reporte de IA se aprueba dos veces?
-->

## Datos del paciente en la factura

El nombre del paciente se guarda cifrado y la cédula solo enmascarada, por ejemplo ******6591. Para buscar una factura se puede usar el nombre, la cédula, el número de factura o el código CUPS. El perfil contable no ve diagnósticos, laboratorios, reportes de IA ni historia clínica: solo lo necesario para cobrar.

<!-- preguntas
¿Por qué el personal de contabilidad no puede ver los resultados de los laboratorios o la historia clínica?
¿Qué datos del usuario me muestra el sistema enmascarados para buscar un cobro?
¿Qué palabras clave puedo meter en el buscador para encontrar un registro de cobro viejito?
¿Hasta dónde llega el acceso del equipo de cobros a la información médica del enfermo?
-->

## Si el módulo no responde

Las facturas viven en MongoDB, aparte de la base clínica. Si MongoDB no está disponible, las pantallas de facturación responden que el servicio no está disponible y el resto del sistema sigue funcionando.

<!-- preguntas
¿Qué hacemos si las pantallas de cobro se caen pero el resto de la historia clínica sigue viva?
¿En qué base de datos distinta a la clínica están guardados todos los registros de cobros?
¿Por qué sale el aviso de que el servicio no está disponible solo en la sección de cobros?
¿Se afecta todo el sistema del hospital si la base de datos de los cobros se llega a caer?
-->
