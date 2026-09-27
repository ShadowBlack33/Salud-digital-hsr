# Mapeo Base de Datos → HL7 FHIR R4

Entregable de interoperabilidad. Documenta cómo cada tabla del modelo
relacional se expone como recurso FHIR y qué terminología usa cada campo.

---

## 1. Sistemas de terminología empleados

| Terminología | URI del `system` | Uso en este sistema |
|---|---|---|
| LOINC | `http://loinc.org` | Códigos de observaciones: signos vitales y laboratorio |
| SNOMED CT | `http://snomed.info/sct` | Procedimientos quirúrgicos y tipos de ubicación |
| CIE-10 | `http://hl7.org/fhir/sid/icd-10` | Diagnóstico de ingreso |
| HL7 v2-0116 | `http://terminology.hl7.org/CodeSystem/v2-0116` | Estado operativo de camas y quirófanos |
| HL7 v3-ActCode | `http://terminology.hl7.org/CodeSystem/v3-ActCode` | Clase y prioridad del encuentro |
| Observation category | `http://terminology.hl7.org/CodeSystem/observation-category` | Categoría de la observación |
| Location physical type | `http://terminology.hl7.org/CodeSystem/location-physical-type` | Cama vs. sala |
| UCUM | `http://unitsofmeasure.org` | Unidades de medida |

**Criterio general:** LOINC para *lo que se mide*, SNOMED CT para *lo que se
hace y dónde*, CIE-10 para *el diagnóstico* (además es el estándar de RIPS en
Colombia).

---

## 2. `pacientes` → `Patient`

| Columna | Elemento FHIR | Nota |
|---|---|---|
| `documento_cifrado` | `identifier[0].value` | Se descifra solo al construir el recurso |
| `tipo_documento` | `identifier[0].type` | Sistema v2-0203, código `NI` |
| `nombre_cifrado` | `name[0].given[0]` | |
| `apellido_cifrado` | `name[0].family` | |
| `sexo` | `gender` | M→male, F→female, O→other |
| `fecha_nacimiento` | `birthDate` | |
| `telefono_cifrado` | `telecom[0].value` | `system: phone` |
| `activo` | `active` | Refleja el soft delete |

---

## 3. `encuentros` → `Encounter`

| Columna | Elemento FHIR | Terminología |
|---|---|---|
| `uuid` | `identifier[0].value` | — |
| `estado` | `status` | Valores FHIR nativos |
| `tipo` | `class` | v3-ActCode |
| `origen` | `priority` | v3-ActCode (`UR` si urgencia) |
| `paciente_id` | `subject.reference` | → `Patient/{id}` |
| `hora_real_inicio` / `hora_real_fin` | `period.start` / `period.end` | Con respaldo en las horas programadas |
| `procedimiento_id` | `reasonCode[0]` | SNOMED CT |
| `diagnostico_cie10_id` | `reasonCode[1]` | CIE-10 |
| `quirofano_id` | `location[0].location` | → `Location/qx-{id}` |
| `cama_id` | `location[1].location` | → `Location/cama-{id}` |
| `medico_responsable_id` | `participant[0].individual` | → `Practitioner/{id}` |

**Mapeo de `tipo` a `Encounter.class`:**

| Valor interno | Código | Display |
|---|---|---|
| `urgencias` | `EMER` | emergency |
| `hospitalizacion` | `IMP` | inpatient encounter |
| `consulta_externa` | `AMB` | ambulatory |
| `cirugia` | `SS` | short stay |

Los estados internos coinciden deliberadamente con el value set de
`Encounter.status`: `planned → arrived → triaged → in-progress → finished`,
con `cancelled` como estado terminal que enlaza con la tabla `cancelaciones`.

---

## 4. `observaciones` → `Observation`

| Columna | Elemento FHIR | Terminología |
|---|---|---|
| `codigo_loinc` | `code.coding[0].code` | LOINC |
| `categoria` | `category[0]` | observation-category |
| `valor_numerico` | `valueQuantity.value` | — |
| `unidad_ucum` | `valueQuantity.code` | UCUM |
| `es_critico` | `interpretation` | Código `AA` (Critical abnormal) |
| `fecha_hora` | `effectiveDateTime` | — |
| `encuentro_id` | `encounter.reference` | → `Encounter/{id}` |

**Códigos LOINC utilizados** (perfil oficial FHIR Vital Signs):

| LOINC | Signo vital | Unidad UCUM |
|---|---|---|
| `8867-4` | Frecuencia cardíaca | `/min` |
| `9279-1` | Frecuencia respiratoria | `/min` |
| `8310-5` | Temperatura corporal | `Cel` |
| `8480-6` | Presión arterial sistólica | `mm[Hg]` |
| `8462-4` | Presión arterial diastólica | `mm[Hg]` |
| `59408-5` | Saturación de O₂ por pulsioximetría | `%` |

---

## 5. `camas` y `quirofanos` → `Location` ⭐

Este es el mapeo más relevante de la propuesta.

FHIR R4 define `Location.operationalStatus` con el value set HL7 v2-0116,
cuyos códigos corresponden **exactamente** a los estados de cama y quirófano
que el sistema gestiona. Es decir: el estándar internacional ya contempla
nativamente el problema de gestión de capacidad que aborda este proyecto, lo
que confirma que no es un caso particular sino un flujo reconocido.

| Estado interno | Código v2-0116 | Display |
|---|---|---|
| `disponible`, `reservada` | `U` | Unoccupied |
| `ocupada`, `en_cirugia`, `en_preparacion`, `en_proceso_alta` | `O` | Occupied |
| `en_limpieza` | `H` | Housekeeping |
| `bloqueada`, `bloqueado` | `C` | Closed |
| `contaminada` | `K` | Contaminated |
| `aislamiento` | `I` | Isolated |

Otros elementos:

| Columna | Elemento FHIR | Valor |
|---|---|---|
| `codigo` | `identifier[0].value` | — |
| `activo` | `status` | active / inactive |
| `tipo_cama.codigo_snomed` | `type[0].coding[0]` | SNOMED CT (`309904001` = UCI) |
| (camas) | `physicalType` | `bd` (Bed) |
| (quirófanos) | `physicalType` | `ro` (Room) |

---

## 6. `personal` → `Practitioner`

| Columna | Elemento FHIR |
|---|---|
| `uuid` | `identifier[0].value` |
| `nombre_cifrado` | `name[0].given[0]` |
| `apellido_cifrado` | `name[0].family` |
| `activo` | `active` |

---

## 7. `log_auditoria` → `AuditEvent`

Mapeo adicional, no exigido, que expone la trazabilidad en formato estándar.

| Columna | Elemento FHIR |
|---|---|
| `operacion` | `action` (C/R/U/D/E) |
| `timestamp` | `recorded` |
| `resultado` | `outcome` (`0` éxito, `4` fallo) |
| `usuario_id` | `agent[0].who` |
| `ip_origen` | `agent[0].network.address` |
| `entidad_tipo` / `entidad_id` | `entity[0].what` |

Disponible en `GET /auditoria/fhir/AuditEvent` como `Bundle` de tipo
`searchset`.

---

## 8. Endpoints de integración

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/fhir/preview/paciente/{id}` | Ver el recurso sin enviarlo a HAPI |
| `GET` | `/fhir/preview/cama/{id}` | Ver el `Location` de una cama |
| `POST` | `/fhir/sync/paciente/{id}` | Crear o actualizar `Patient` en HAPI |
| `POST` | `/fhir/sync/encuentro/{id}` | Crear o actualizar `Encounter` |
| `POST` | `/fhir/sync/observacion/{id}` | Crear `Observation` |
| `POST` | `/fhir/sync/cama/{id}` | Publicar estado como `Location` |
| `POST` | `/fhir/sync/bundle/paciente/{id}` | Bundle transaccional atómico |
| `GET` | `/fhir/Patient/{fhir_id}` | Leer desde HAPI |
| `GET` | `/fhir/buscar/{tipo}?...` | Búsqueda parametrizada |
| `GET` | `/fhir/{tipo}/{id}/_history` | Historial de versiones nativo de FHIR |

**Idempotencia:** cada tabla sincronizable guarda el identificador devuelto
por HAPI (`fhir_patient_id`, `fhir_encounter_id`, `fhir_location_id`). Si ya
existe, la operación es un `PUT` (actualización) en lugar de un `POST`; sin
esto, cada sincronización crearía duplicados.

---

## 9. Pendiente de verificación

Los códigos SNOMED CT del catálogo de procedimientos y de las especialidades
están como `NULL` a la espera de verificación en el navegador oficial
(`https://browser.ihtsdotools.org/`).

Se dejaron deliberadamente vacíos en lugar de rellenarlos de memoria: un
código clínico incorrecto en un sistema de salud es peor que la ausencia del
código, porque induce a error a quien consuma la información.

Los códigos ya verificados contra documentación oficial de SNOMED
International son:

- `22232009` — Hospital (environment)
- `309904001` — Intensive care unit (environment)
