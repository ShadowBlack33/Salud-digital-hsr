# Mapa normativo · Pulso (Hospital San Rafael)

R22 · Responsable: Juan José García (Ingeniería Biomédica).

Este documento conecta cada norma colombiana que aplica al sistema con lo que exige,
el control técnico que la responde, cómo se comprueba y qué falta. Todo el sistema
trabaja con **datos sintéticos** sobre un hospital hipotético: el mapa muestra que el
diseño cumple o deja el camino listo para cumplir, no que exista una habilitación real.

> **Regla de redacción.** Solo se citan artículos que verificamos en la fuente. Donde
> dice *(verificar numeral)* el contenido de la norma es correcto pero el número exacto
> del artículo se confirma en la fuente oficial antes de citarlo en voz alta.

## 1. Resumen

| Norma | Tema | Qué responde en Pulso |
|---|---|---|
| Ley 1581 de 2012 | Protección de datos personales; los de salud son sensibles | Cifrado, control de acceso por rol, seudonimización hacia la IA, auditoría, consentimiento |
| Decreto 1377 de 2013 (compilado en el Decreto 1074 de 2015) | Reglamenta la Ley 1581: autorización y responsabilidad demostrada | Registro del consentimiento con fecha, trazabilidad completa |
| Ley 2015 de 2020 | Historia clínica electrónica interoperable | HL7 FHIR R4 con HAPI, recursos y terminologías estándar |
| Resolución 866 de 2021 | Elementos de datos clínicos para la interoperabilidad | Paciente, encuentro, observación con LOINC, procedimiento con SNOMED CT, diagnóstico CIE-10 |
| Resolución 1995 de 1999 | Manejo de la historia clínica | Integridad (soft delete, historial), confidencialidad, acceso restringido, PDF de la historia |
| Resolución 839 de 2017 | Retención de la historia clínica | Nada se borra físicamente; plazo de 15 años como política |
| Resolución 3100 de 2019 | Habilitación de servicios de salud | Soporte a los estándares de procesos prioritarios e historia clínica (no habilita por sí mismo) |
| Resolución 256 de 2016 | Sistema de información para la calidad | Indicador de cancelación de cirugía programada en el tablero |
| Resolución 4816 de 2008 | Tecnovigilancia | Bloqueo de quirófanos y camas por mantenimiento con motivo y auditoría |

## 2. Matriz norma → exigencia → control → evidencia

### Ley 1581 de 2012 · Protección de datos personales

| Exigencia | Control en Pulso | Cómo se comprueba | Qué falta |
|---|---|---|---|
| Los datos de salud son **datos sensibles** (art. 5) y su tratamiento tiene reglas especiales (art. 6) | Nombre, documento, teléfono, correo y dirección se guardan cifrados con AES-256-GCM; el documento se busca por índice ciego (HMAC), nunca en claro | `docs/SEGURIDAD.md`; en la base las columnas `*_cifrado` no son legibles | Claves en variables de entorno, no en un gestor de llaves (KMS) |
| Principio de **acceso y circulación restringida** (art. 4) | Control por rol en la API: el médico ve solo sus pacientes, el contable no ve datos clínicos, el paciente solo los suyos | Pruebas de R03 en `scripts/test_e2e.py` (403 al contable en la historia, 403/404 al paciente con datos ajenos) | — |
| Principio de **finalidad** (art. 4): usar los datos solo para lo que se recogieron | Capa de seudonimización hacia la IA: al modelo solo van variables clínicas y un id seudónimo | R12: `GET /ia/reportes/{id}/payload` muestra el JSON exacto; prueba "canario" en `scripts/probar_seudonimizacion.py` | — |
| Principios de **seguridad** y **confidencialidad** (art. 4) | Contraseñas con Argon2id, sesión de 15 min revocable, bloqueo a los 3 intentos, CORS cerrado, cabeceras de seguridad, límite de peticiones | R02 y R03 en el tester; `front/nginx/default.conf` | Doble factor de autenticación |
| **Autorización** previa, expresa e informada del titular (art. 9) | Campo `consentimiento_datos` con su fecha al crear el paciente | Ficha del paciente y auditoría de la creación | Con datos sintéticos el consentimiento es simulado; en producción iría firma o documento soporte |
| **Deberes del responsable**: conservar la información con seguridad y evitar su pérdida o acceso no autorizado (art. 17) | Auditoría append-only protegida por trigger; soft delete (nada se borra) | R13 y R14 | Copias de respaldo y alta disponibilidad fuera del Corte 2 |

### Decreto 1377 de 2013 · Reglamento de la Ley 1581

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| Autorización para datos sensibles, que se pueda consultar después *(verificar numeral)* | Consentimiento con fecha guardado en el paciente | Ficha y auditoría | Texto de la autorización versionado |
| **Responsabilidad demostrada**: poder probar las medidas tomadas *(verificar numeral)* | Auditoría de cada acción relevante (quién, qué, cuándo, desde dónde), sin guardar datos sensibles en el log | `GET /auditoria` (solo admin); `docs/SEGURIDAD.md` | Política escrita de tratamiento de datos |

### Ley 2015 de 2020 · Historia clínica electrónica interoperable

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| La historia clínica electrónica debe ser **interoperable** entre prestadores | Servidor HL7 FHIR R4 (HAPI); pacientes, encuentros, observaciones, ubicaciones y remisiones (`ServiceRequest`) en recursos estándar | R15 y R21; `docs/MAPEO_FHIR.md` | Conexión real con el mecanismo nacional de interoperabilidad (IHCE) |
| Seguridad y confidencialidad en el intercambio | `/fhir` cerrado detrás de la API: sin token solo `POST Observation`, `metadata` y búsqueda exacta de paciente; `DELETE` nunca | Puerta de nginx (`/_puerta_fhir`); `docs/SEGURIDAD.md` | SMART on FHIR (OAuth2 con scopes FHIR) |

### Resolución 866 de 2021 · Datos clínicos para la interoperabilidad

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| Conjunto mínimo de datos clínicos relevantes para intercambiar | Identificación del paciente, encuentro, signos y laboratorios con LOINC, procedimientos con SNOMED CT, diagnóstico CIE-10 | `docs/MAPEO_FHIR.md` | Validar que cada elemento del anexo técnico esté cubierto; códigos SNOMED de algunos procedimientos pendientes de confirmar |

### Resolución 1995 de 1999 · Manejo de la historia clínica

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| Características de **integralidad, secuencialidad y disponibilidad** | Historia del paciente en JSON y PDF con observaciones y reportes de IA **aprobados** | R11: `GET /pacientes/{id}/historia/pdf` | — |
| Lo registrado **no se altera ni se borra** | Soft delete, edición con historial, restauración solo por admin | R14; `GET /pacientes/{id}/historial` | — |
| **Confidencialidad** y acceso solo de quien está autorizado | Acceso por rol y por relación con el paciente; el especialista pierde el acceso al rechazar una remisión | R03 y R08 | Acceso de emergencia ("break-the-glass") auditado |
| Lo que entra a la historia lo **valida un profesional** | El reporte de IA queda `pendiente` hasta que un médico lo aprueba; el rechazado se conserva como evidencia | R10 | Firma digital del profesional |

### Resolución 839 de 2017 · Retención de la historia clínica

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| Conservar la historia clínica por **15 años** desde la última atención | Ningún registro clínico se borra físicamente (soft delete) | R14 | Política automática de archivo y depuración al vencer el plazo |

### Resolución 3100 de 2019 · Habilitación

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| Estándares de historia clínica y registros, y de procesos prioritarios para habilitar servicios | Pulso apoya estos estándares (trazabilidad, acceso controlado, coordinación de camas y quirófanos), pero un software no habilita un servicio | Toda la matriz anterior | La habilitación es del prestador; no se citan numerales específicos |

### Resolución 256 de 2016 · Calidad en salud

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| Reportar indicadores de calidad, entre ellos la cancelación de cirugía programada (P.2.15) | El tablero del coordinador calcula la proporción del último mes cerrado | Tablero "Hospital" | Reporte oficial a la Superintendencia |

### Resolución 4816 de 2008 · Tecnovigilancia

| Exigencia | Control | Evidencia | Qué falta |
|---|---|---|---|
| Gestionar los eventos e incidentes con dispositivos médicos | Un quirófano o cama se marca bloqueado o en mantenimiento con motivo, queda en la auditoría y no se puede reservar | Cambio de estado en camas y quirófanos; auditoría | Registro de eventos adversos con dispositivos y reporte al INVIMA |

## 3. Lo que declaramos como limitación

Se dicen en la sustentación como camino de evolución, no como algo que funcione:

- Acceso de emergencia ("break-the-glass") con motivo y tiempo limitado.
- `Consent` y `Provenance` de FHIR para el consentimiento y la procedencia de cada dato.
- Resumen Digital de Atención (RDA) y sus plazos: pendiente de verificar en la norma vigente.
- Firma digital del profesional y del paciente.
- RIPS y factura electrónica: la facturación de Pulso es una referencia interna, no un RIPS ni una factura electrónica. Antes de citar la norma vigente de RIPS/FEV, confirmar si la Res. 948 de 2026 reemplazó a la Res. 2275 de 2023.
- Doble factor de autenticación y gestión de llaves en un KMS.
- Alta disponibilidad y copias de respaldo.

## 4. Preguntas que puede hacer el jurado

- **¿Qué exige cada norma y qué no cubrimos?** Sección 2, columna "Qué falta".
- **¿Por qué la IA no viola la Ley 1581?** Porque al modelo no le llega ningún dato que identifique al paciente (principio de finalidad) y el payload exacto queda guardado para demostrarlo (R12).
- **¿Puede la IA escribir en la historia clínica?** No. Solo lo que un médico aprueba entra a la historia (Res. 1995: lo registrado lo valida un profesional).
- **¿Qué pasa si se borra un paciente?** Nada se borra físicamente; solo el admin restaura y todo queda auditado (Res. 1995 y Res. 839).
