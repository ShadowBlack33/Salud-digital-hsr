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

## Estados de una factura

Una factura nace pendiente. Puede pasar a radicada cuando se presenta a la entidad, a glosada si la entidad la objeta y a pagada cuando se recibe el pago; se puede marcar como pagada desde pendiente, radicada o glosada. También se puede anular con un motivo de al menos 5 caracteres. Una factura pagada no se puede anular: no existe nota crédito.

## Tipos de cobro

Los tipos de cobro son consulta, urgencias, hospitalización, cirugía, imagenología, laboratorio, medicamentos, insumos, terapia, análisis de IA, remisión y otros. El tarifario tiene 40 servicios con su código y su valor de referencia.

## Quién paga: cobertura y reparto del valor

La cobertura puede ser particular, EPS, régimen especial, SOAT o medicina prepagada. Un paciente particular paga todo. Con SOAT o régimen especial el paciente paga 0. Con prepagada paga el menor valor entre el servicio y 35.000 pesos. En consulta y urgencias con EPS paga la cuota moderadora: Pulso usa como referencia interna 4.700 pesos en el régimen contributivo (el valor de 2025 del rango de menos de 2 salarios mínimos) y 0 en el subsidiado. En los demás servicios con EPS paga un copago del 11,5 % en el contributivo y del 10 % en el subsidiado; el resto lo paga la entidad. Los valores oficiales vigentes, por rango de ingreso y con sus topes, están en la guía de cuotas moderadoras y copagos.

## Factura automática del análisis de IA

Cuando un médico aprueba un reporte de IA, se crea sola una factura del análisis (código IA0001) ligada a ese reporte. Un reporte solo puede tener una factura: si la aprobación llega dos veces, se devuelve la factura que ya existía y no se cobra doble. Un reporte rechazado no se factura.

## Datos del paciente en la factura

El nombre del paciente se guarda cifrado y la cédula solo enmascarada, por ejemplo ******6591. Para buscar una factura se puede usar el nombre, la cédula, el número de factura o el código CUPS. El perfil contable no ve diagnósticos, laboratorios, reportes de IA ni historia clínica: solo lo necesario para cobrar.

## Si el módulo no responde

Las facturas viven en MongoDB, aparte de la base clínica. Si MongoDB no está disponible, las pantallas de facturación responden que el servicio no está disponible y el resto del sistema sigue funcionando.
