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

<!-- preguntas
¿Cómo protege el sistema la información médica y los datos personales de los pacientes guardados?
¿De qué manera se asegura el documento de identidad en la base de datos sin descifrarlo?
¿Qué tipo de resguardo tienen los números telefónicos y los correos electrónicos dentro de la aplicación?
¿Cómo se maneja la privacidad de los historiales médicos y la información clínica de los usuarios?
-->

## Contraseñas y sesiones

Las contraseñas se guardan con Argon2id (64 MiB de memoria, 3 iteraciones, paralelismo 4) y deben tener al menos 12 caracteres con mayúscula, minúscula, dígito y carácter especial. Tras 3 intentos fallidos la cuenta se bloquea hasta que un administrador la desbloquea, y el bloqueo avisa al admin. El token de acceso dura 15 minutos y el de renovación 7 días; este rota en cada uso y se revoca al cerrar sesión o cambiar la contraseña. La sesión se cierra tras 15 minutos sin actividad.

<!-- preguntas
¿Cuántos errores de clave tolera la plataforma antes de dejar la cuenta inactiva para el usuario?
¿Qué tan complejos deben ser los códigos de acceso de los colaboradores y cuánto duran activos?
¿Cómo actúa el software cuando pasa un rato sin que el personal interactúe con la pantalla?
¿De qué forma se guardan las claves de ingreso de los funcionarios para evitar filtraciones graves?
-->

## Autorización en dos niveles

Nivel 1: el rol debe tener el permiso del recurso y la acción. Nivel 2: según el alcance (todos, los propios, los asignados o los de sí mismo), se verifica que pueda tocar ese registro en particular; así un médico no puede ver los pacientes de otro. Los permisos viven en la base de datos (roles, permisos y roles_permisos), no en el código.

<!-- preguntas
¿Por qué motivo un galeno no puede revisar la historia clínica de un enfermo que no le corresponde?
¿Cómo evalúa el sistema si un empleado tiene el derecho de mirar o modificar un registro?
¿Dónde quedan guardadas las autorizaciones y los perfiles de acceso que tiene cada trabajador?
¿De qué manera se comprueba que el alcance del rol permita tocar una historia en particular?
-->

## Trazabilidad

El log de auditoría es de solo agregar: un trigger de la base impide modificarlo o borrarlo, incluso al admin. Nada clínico se borra físicamente (soft delete), cada edición guarda el valor anterior y solo el admin restaura. La auditoría registra quién hizo qué, sobre qué registro y desde dónde, sin guardar datos sensibles.

<!-- preguntas
¿Cómo se garantiza que nadie pueda alterar o borrar el historial de acciones hechas en la plataforma?
¿Qué ocurre cuando se elimina un dato clínico y cómo se puede recuperar esa información después?
¿Dónde queda registrado qué funcionario hizo un cambio, a qué hora y desde qué computador?
¿Puede un administrador del sistema alterar los registros de auditoría si comete un error grave?
-->

## Interoperabilidad segura

El servidor FHIR (HAPI) está detrás de la API: sin token solo se lee la metadata; leer exige el permiso fhir:read y escribir, incluida la publicación de resultados de un laboratorio externo, exige la cuenta de integración. El paciente se identifica en FHIR con su número de historia (MRN) y no con la cédula, y los resultados externos se guardan en las observaciones del paciente.

<!-- preguntas
¿Qué se necesita para que un laboratorio externo pueda mandar resultados de exámenes a la plataforma?
¿Cómo se reconoce a una persona en el servidor FHIR sin usar su número de cédula tradicional?
¿Qué permisos debe tener una entidad externa para consultar la pasarela de intercambio de datos?
¿Dónde van a parar los reportes y exámenes que envían sistemas de salud de afuera del hospital?
-->

## Mapa normativo

Ley 1581 de 2012 y Decreto 1377 de 2013: cifrado, acceso restringido, seudonimización hacia la IA, consentimiento con fecha y auditoría. Ley 2015 de 2020 y Resolución 866 de 2021: historia clínica interoperable con HL7 FHIR R4, LOINC, SNOMED CT y CIE-10. Resolución 1995 de 1999 y Resolución 839 de 2017: la historia no se altera ni se borra y se conserva al menos 15 años. Resolución 256 de 2016: indicador de cancelación de cirugía en el tablero. Resolución 4816 de 2008: bloqueo de quirófanos y camas por mantenimiento con motivo y auditoría.

<!-- preguntas
¿Por cuánto tiempo hay que guardar obligatoriamente los expedientes médicos según las leyes colombianas?
¿Qué normas rigen el uso de historias clínicas electrónicas y su intercambio con otros centros médicos?
¿Cuáles son las leyes de protección de datos que obligan a cifrar la información de los usuarios?
¿Qué resoluciones regulan el bloqueo de quirófanos por mantenimiento y el indicador de cirugías canceladas?
-->

## Limitaciones declaradas

Las claves están en variables de entorno y no en un gestor de llaves (KMS); no hay doble factor de autenticación; no hay acceso de emergencia (break-the-glass) auditado; falta SMART on FHIR; la facturación es una referencia interna, no RIPS ni factura electrónica; y faltan alta disponibilidad y copias de respaldo.

<!-- preguntas
¿Qué funciones de seguridad importantes le hacen falta actualmente al software del hospital?
¿Cómo se manejan las llaves de cifrado y por qué no se usa un gestor especializado?
¿Qué pasa si un médico necesita entrar de urgencia a un expediente sin tener los permisos habituales?
¿El sistema actual ya genera la facturación electrónica y los reportes obligatorios para el ministerio?
-->
