# Contrato de facturación entre el front y el módulo contable (R09)

El módulo contable (MongoDB, a cargo de Sara) puede cumplir solo lo mínimo del
enunciado y la pantalla funciona. Para que la facturación sirva a escala de
hospital (miles de movimientos al día), el front ya usa estos campos y
parámetros; mientras la ruta no exista, muestra datos de demostración.

## Documento `factura`

| Campo | Obligatorio (R09) | Ejemplo | Para qué |
|---|---|---|---|
| `id` | sí | `"F-250081"` | |
| `paciente_id` | sí | `documento_bidx` | Llave del paciente (nunca la cédula) |
| `servicio` | sí | `"laboratorio"`, `"analisis_ia"` | Compatibilidad con el tester |
| `valor` | sí | `88000` | Total en COP |
| `fecha` | sí | ISO 8601 | |
| `estado_pago` | sí | `pendiente` · `radicada` · `glosada` · `pagada` · `anulada` | |
| `reporte_id` | en las automáticas | `412` | Factura creada al aprobar un reporte de IA (R19) |
| `tipo_cobro` | no | `consulta` · `urgencias` · `hospitalizacion` · `cirugia` · `imagenologia` · `laboratorio` · `medicamentos` · `insumos` · `terapia` · `ia` · `remision` · `otros` | Primer filtro de la pantalla |
| `cups` | no | `"904902"` | Código del servicio en el tarifario |
| `descripcion` | no | `"Gases arteriales"` | |
| `cantidad`, `valor_unitario` | no | `2`, `44000` | |
| `paciente_nombre`, `paciente_documento` | no | `"Andrés Caicedo"`, `"****6591"` | Se guardan al facturar: el contable no consulta la tabla de pacientes |
| `cobertura` | no | `{"tipo": "eps", "entidad": "EPS Gamma", "regimen": "subsidiado"}` | Particular o la entidad que responde. `tipo`: `particular` · `eps` · `especial` · `soat` · `prepagada` |
| `valor_paciente`, `valor_entidad` | no | `8800`, `79200` | Lo que paga el paciente (copago, cuota moderadora o todo si es particular) y lo que paga la entidad |
| `origen` | no | `manual` · `automatica` | |

Si faltan `tipo_cobro`, `cobertura` o el reparto, el front los deduce (ver
`front/src/lib/facturacion.js`, función `normalizarFactura`).

## Rutas

- `GET /contabilidad/facturas` — lista. Acepta, opcionalmente, `tipo`,
  `estado`, `entidad`, `q` (nombre, documento, factura o CUPS), `desde`,
  `hasta`, `pagina`, `por_pagina`. Puede responder una lista simple (el front
  filtra y pagina) o `{"facturas": [...], "total": N}` ya filtrada y paginada.
- `POST /contabilidad/facturas` — crea (cuerpo con los campos de arriba).
- `PATCH /contabilidad/facturas/{id}/pagar`
- `PATCH /contabilidad/facturas/{id}/anular` — cuerpo `{"motivo": "..."}`.
- `GET /contabilidad/tarifario` — `[{codigo, nombre, tipo_cobro, valor}]`.

Solo `contable` y `admin` operan estas rutas (R09). El paciente ve sus cobros
en `GET /mi-cuenta` (ya existe en la API, `app/api/perfiles.py`).

## Índices sugeridos en MongoDB

`{fecha: -1}`, `{tipo_cobro: 1, estado_pago: 1, fecha: -1}`,
`{"cobertura.entidad": 1, estado_pago: 1}`, `{paciente_id: 1, fecha: -1}`.
