# Rutas de IA para el `tester.yaml` (R10, R11, R12, R20)

> Para quien arme el `tester.yaml` a partir de `plantilla_equipo.yaml`. Las rutas son
> relativas a la API (detrás de nginx: `https://<url>/api`). Los nombres de las llaves
> (`ia_analizar`, `historia_pdf`…) son los del contrato de REQUISITOS.md, sección 7.

| Llave del contrato | Método y ruta | Cuerpo | Respuesta |
|---|---|---|---|
| `ia_analizar` | `POST /ia/analizar` | `{"paciente_id": "<id>"}` y opcional `"variables": {...}` | `201 {"id", "estado": "pendiente", "critico", "probabilidad", "alerta_id"}` |
| `ia_reporte` | `GET /ia/reportes/{id}` | — | `{"id", "estado": "pendiente" \| "aprobado" \| "rechazado", ...}` |
| `ia_payload` | `GET /ia/reportes/{id}/payload` | — | `{"reporte_id", "payload": {"pseudo_id", "variables": {...}}}` |
| (aprobar) | `POST /ia/reportes/{id}/aprobar` | `{"observaciones": "..."}` | `200`, estado `aprobado`. `paciente` y `contable`: 403. Segunda vez: 409 |
| (rechazar) | `POST /ia/reportes/{id}/rechazar` | `{"observaciones": "..."}` | `200`, estado `rechazado` |
| `historia` | `GET /pacientes/{id}/historia` | — | JSON con `reportes_ia` (solo aprobados, cada uno con `id`) |
| `historia_pdf` | `GET /pacientes/{id}/historia/pdf` | — | `Content-Type: application/pdf`, con el nombre del paciente como texto |
| `alertas` | `GET /alertas` | — | `{"alertas": [{"id", "paciente_id", "nivel", "estado": "activa" \| "reconocida", ...}]}` |
| `alerta_reconocer` | `POST /alertas/{id}/reconocer` | `{"nota": "..."}` (mínimo 3 caracteres) | `200`, estado `reconocida`. Segunda vez: 409 |

Extras que usa el front (no están en el contrato):

- `GET /ia/reportes?paciente_id=<id>`: todos los reportes de un paciente.
- `GET /ia/reportes?estado=pendiente`: los reportes por revisar.

## `paciente_critico`

Valores que con el modelo `provisional-0` garantizan `critico: true` (probabilidad 0,999,
umbral 0,30). Detalle y justificación en `ml/UMBRAL.md`.

| Variable | Valor | Cómo entra al sistema |
|---|---|---|
| Fecha de nacimiento | 1948-03-02 (78 años) | Al crear el paciente |
| Sexo | F | Al crear el paciente |
| Glucosa | 42 mg/dL | Observación LOINC `2339-0` |
| Potasio | 6,6 mmol/L | Observación LOINC `2823-3` |
| Hemoglobina | 6,8 g/dL | Observación LOINC `718-7` |

**Cómo llegan los valores al modelo.** `POST /ia/analizar` usa, en este orden:

1. Los valores enviados en la petición, si vienen:
   `{"paciente_id": "<id>", "variables": {"glucosa": 42, "potasio": 6.6, "hemoglobina": 6.8}}`
2. Si no, las últimas **observaciones registradas** del paciente (LOINC de la tabla).

Edad y sexo siempre salen del paciente. Los valores de la petición pasan por la misma
lista permitida: una llave como `nombre` o `telefono` se descarta y nunca llega al
payload. Si no hay ningún laboratorio por ninguna de las dos vías, la respuesta es 422
("sin laboratorios no hay predicción"), porque con todo imputado el modelo estaría
inventando el riesgo.

Así, el tester puede mandar `paciente_critico` en el cuerpo del análisis, o crear antes
las observaciones; las dos formas funcionan. Conviene confirmar en `plantilla_equipo.yaml`
cuál usa.

## Usuarios de prueba que usa esta parte

`medico01` y `especialista01` (analizan, aprueban y reconocen), `paciente_demo` y
`contable01` (deben recibir 403), y `admin` (consulta la auditoría).
