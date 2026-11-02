---
id: G18
titulo: Seguridad, protección de datos y normativa de Pulso
fuente: Equipo Pulso (Universidad Autónoma de Occidente). Documentación del proyecto: docs/SEGURIDAD.md y docs/NORMATIVA.md, 2026. Ley 1581 de 2012, Decreto 1377 de 2013, Ley 2015 de 2020, Resolución 866 de 2021.
url: https://github.com/ShadowBlack33/Salud-digital-hsr
tipo: guia
audiencia: admin
---

# Seguridad, protección de datos y normativa de Pulso

Documento interno para el administrador, resumido por el equipo de Pulso a partir de la documentación de seguridad y del mapa normativo del proyecto.

## Datos sensibles y cifrado

La Ley 1581 de 2012 clasifica los datos de salud como sensibles. En Pulso, documento, nombres, apellidos, teléfono, correo, dirección y registro profesional se guardan cifrados con AES-256-GCM a nivel de aplicación, con un dato asociado (AAD) por campo para que un valor cifrado no se pueda mover a otra columna. La cédula se busca con un índice ciego (HMAC-SHA256), sin descifrarla. Los datos clínicos no se cifran pero tienen acceso restringido por rol y quedan en la auditoría.

## Contraseñas y sesiones

Las contraseñas se guardan con Argon2id (64 MiB de memoria, 3 iteraciones, paralelismo 4) y deben tener al menos 12 caracteres con mayúscula, minúscula, dígito y carácter especial. Tras 3 intentos fallidos la cuenta se bloquea hasta que un administrador la desbloquea, y el bloqueo avisa al admin. El token de acceso dura 15 minutos y el de renovación 7 días; este rota en cada uso y se revoca al cerrar sesión o cambiar la contraseña. La sesión se cierra tras 15 minutos sin actividad.

## Autorización en dos niveles

Nivel 1: el rol debe tener el permiso del recurso y la acción. Nivel 2: según el alcance (todos, los propios, los asignados o los de sí mismo), se verifica que pueda tocar ese registro en particular; así un médico no puede ver los pacientes de otro. Los permisos viven en la base de datos (roles, permisos y roles_permisos), no en el código.

## Trazabilidad

El log de auditoría es de solo agregar: un trigger de la base impide modificarlo o borrarlo, incluso al admin. Nada clínico se borra físicamente (soft delete), cada edición guarda el valor anterior y solo el admin restaura. La auditoría registra quién hizo qué, sobre qué registro y desde dónde, sin guardar datos sensibles.

## Interoperabilidad segura

El servidor FHIR (HAPI) está detrás de la API: sin token solo se lee la metadata; leer exige el permiso fhir:read y escribir, incluida la publicación de resultados de un laboratorio externo, exige la cuenta de integración. El paciente se identifica en FHIR con su número de historia (MRN) y no con la cédula, y los resultados externos se guardan en las observaciones del paciente.

## Mapa normativo

Ley 1581 de 2012 y Decreto 1377 de 2013: cifrado, acceso restringido, seudonimización hacia la IA, consentimiento con fecha y auditoría. Ley 2015 de 2020 y Resolución 866 de 2021: historia clínica interoperable con HL7 FHIR R4, LOINC, SNOMED CT y CIE-10. Resolución 1995 de 1999 y Resolución 839 de 2017: la historia no se altera ni se borra y se conserva al menos 15 años. Resolución 256 de 2016: indicador de cancelación de cirugía en el tablero. Resolución 4816 de 2008: bloqueo de quirófanos y camas por mantenimiento con motivo y auditoría.

## Limitaciones declaradas

Las claves están en variables de entorno y no en un gestor de llaves (KMS); no hay doble factor de autenticación; no hay acceso de emergencia (break-the-glass) auditado; falta SMART on FHIR; la facturación es una referencia interna, no RIPS ni factura electrónica; y faltan alta disponibilidad y copias de respaldo.
