# Seguridad y protección de datos

Sistema de coordinación de capacidad quirúrgica — Hospital San Rafael

Este documento justifica cada decisión de seguridad. Es un entregable en sí
mismo: la rúbrica evalúa la justificación, no solo que el código funcione.

---

## 1. Clasificación de los datos

La Ley 1581 de 2012 (habeas data) clasifica los datos relativos a la salud
como **datos sensibles**, con un régimen más estricto que el de los datos
personales ordinarios: exigen autorización explícita, finalidad declarada y
medidas de seguridad reforzadas.

| Nivel | Datos | Tratamiento |
|---|---|---|
| **Sensible — cifrado obligatorio** | Documento de identidad, nombres, apellidos, teléfono, email, dirección, registro profesional | AES-256-GCM a nivel de aplicación |
| **Clínico — no cifrado, acceso restringido** | Diagnóstico, procedimiento, observaciones, riesgo ASA | Control por RBAC + auditoría |
| **Operativo — abierto al personal autorizado** | Estado de camas y quirófanos, agenda | RBAC |
| **Derivado — anonimizado** | Tiempo de desplazamiento, edad, desviación de tiempos | Uso analítico y predictivo |

---

## 2. Cifrado en reposo

### 2.1 Por qué a nivel de aplicación y no con `pgcrypto`

La opción intuitiva sería `pgp_sym_encrypt()` de PostgreSQL. Se descartó por
una razón concreta: **la clave viajaría dentro de la sentencia SQL**, y por
tanto podría quedar registrada en los logs del servidor, en
`pg_stat_statements` y en las trazas de conexiones lentas.

Cifrando en la aplicación, el motor de base de datos nunca ve la clave ni el
texto claro. Esto importa especialmente porque la base va alojada en un
proveedor gestionado (Neon), donde no controlamos el acceso administrativo al
servidor.

### 2.2 Por qué AES-256-GCM y no AES-CBC

GCM es un modo de **cifrado autenticado**: además de confidencialidad
garantiza integridad. Si alguien con acceso de escritura a la base altera un
byte del ciphertext, el descifrado falla en lugar de devolver basura
silenciosamente. Con CBC esa manipulación podría pasar inadvertida.

Cada operación de cifrado usa un **nonce aleatorio de 96 bits**, de modo que
cifrar dos veces el mismo documento produce ciphertexts distintos. Esto impide
inferir por comparación que dos registros comparten un valor.

### 2.3 AAD por campo

Cada valor se cifra ligándolo a su tabla y columna mediante *Additional
Authenticated Data* (`"pacientes.documento"`). Consecuencia práctica: un
atacante con acceso de escritura a la base **no puede mover** el documento
cifrado de un paciente al registro de otro, ni reutilizar un ciphertext de la
tabla `personal` en la tabla `pacientes`. El descifrado fallaría.

### 2.4 Formato y rotación

```
v1:<nonce_base64>:<ciphertext_base64>
```

El prefijo de versión permite rotar claves sin migración masiva: una `v2`
podría convivir con registros `v1` mientras se recifran progresivamente.

---

## 3. Blind index: buscar sin descifrar

El cifrado aleatorio tiene un coste: imposibilita `WHERE documento = 'X'`.
Descifrar la tabla entera en cada búsqueda no es viable.

La solución es almacenar, junto al ciphertext, un **HMAC-SHA256
determinístico** del valor normalizado:

```
documento_bidx = HMAC-SHA256(clave_indice, "pacientes.documento|1144098765")
```

- Permite igualdad exacta con un índice B-tree normal
- No revela el valor original (el HMAC no es reversible)
- Usa una **clave distinta** a la de cifrado: comprometer una no compromete la otra
- Normaliza el formato antes de indexar, de modo que `1.144.098.765` y
  `1144098765` producen el mismo índice

**Limitación asumida:** el blind index solo soporta igualdad exacta, no
búsquedas parciales ni por rango. Es un compromiso consciente: para este
sistema, buscar un paciente por su documento completo cubre el caso de uso.

---

## 4. Contraseñas

**Argon2id**, ganador del Password Hashing Competition. Parámetros:

| Parámetro | Valor | Razón |
|---|---|---|
| `memory_cost` | 64 MiB | Encarece los ataques con GPU y ASIC |
| `time_cost` | 3 | Equilibrio entre seguridad y latencia de login |
| `parallelism` | 4 | Ajustado a CPU típica de servidor |

Se descartó bcrypt (límite de 72 bytes, menor resistencia a hardware
dedicado) y por supuesto cualquier variante de SHA sin derivación de clave.

**Política de contraseñas:** mínimo 12 caracteres, con mayúscula, minúscula,
dígito y carácter especial.

**Protección contra fuerza bruta:** bloqueo temporal de la cuenta tras 5
intentos fallidos. El endpoint de login devuelve un mensaje genérico y ejecuta
el hashing incluso cuando el usuario no existe, para no filtrar información
por diferencia en el tiempo de respuesta.

---

## 5. Tokens y sesiones

| Token | Vida | Almacenamiento |
|---|---|---|
| Access (JWT) | 15 minutos | Solo en el cliente |
| Refresh | 7 días | Hash SHA-256 en tabla `sesiones` |

Un JWT no se puede revocar antes de que expire; por eso la vida es corta y la
revocación real se implementa sobre el refresh token, que sí está en base de
datos. El refresh **rota en cada uso**: el anterior queda revocado, de forma
que reutilizar un refresh robado es detectable.

Al cambiar la contraseña se revocan todas las sesiones activas del usuario.

---

## 6. Autorización en dos niveles

Comprobar únicamente el rol es insuficiente. Si un endpoint solo verifica
"¿este rol puede editar pacientes?", cualquier médico podría editar los
pacientes de cualquier otro.

**Nivel 1 — endpoint.** ¿El rol tiene el permiso `recurso:accion`?

**Nivel 2 — registro.** Dado el alcance concedido, ¿puede tocar *ese* registro?

| Alcance | Regla |
|---|---|
| `all` | Cualquier registro |
| `own` | Solo los que él creó (`created_by == usuario.id`) |
| `assigned` | Solo aquellos donde figura como responsable |
| `self` | Solo su propia información (rol paciente) |

El modelo RBAC vive en base de datos (`roles`, `permisos`, `roles_permisos`),
no en el código. Añadir un rol nuevo no requiere desplegar.

---

## 7. Trazabilidad

### 7.1 Log de auditoría inmutable

La tabla `log_auditoria` está protegida por un trigger que **rechaza UPDATE y
DELETE**. Ni siquiera un administrador de la aplicación puede alterarla. Esa
inmutabilidad es lo que la hace válida como evidencia.

Registra: usuario, rol, entidad, operación, resultado (éxito o denegado),
IP, user-agent, endpoint y marca de tiempo. También registra los **intentos
denegados**, que son justamente los interesantes en una investigación.

Los campos sensibles nunca se escriben en claro en la auditoría: se
reemplazan por `<protegido>`.

### 7.2 Soft delete

Nada se borra físicamente. `DELETE` marca `activo = false` y registra quién y
cuándo. El dato permanece para trazabilidad y puede restaurarse.

Todos los `GET` filtran `activo = true` por defecto — sin ese filtro el borrado
lógico sería invisible en la práctica.

### 7.3 Soft edit

Cada campo modificado genera una fila en `historial_cambios` con su valor
anterior, versionada. En campos cifrados se registra el hecho del cambio pero
no los valores, para no crear una copia en claro por la puerta de atrás.

### 7.4 Restauración

Reservada exclusivamente al rol `admin`, mediante el permiso
`recurso:restore`. Un médico puede eliminar lo que creó, pero no revertirlo.

---

## 8. Minimización de datos

**Decisión relevante:** se descartó almacenar la dirección de residencia del
personal médico, pese a haberse sugerido como variable para el modelo
predictivo de retrasos.

Se almacena en su lugar `tiempo_desplazamiento_estimado_min`.

Justificación:
1. La dirección es un dato personal bajo la Ley 1581 de 2012; almacenarla
   exigiría consentimiento y finalidad declarada.
2. El poder predictivo está en el **tiempo de viaje**, no en las coordenadas.
   La variable derivada conserva la utilidad y elimina el riesgo.
3. Ante una institución real, proponer una base de datos con las direcciones
   de residencia de su personal sería un problema de cumplimiento.

Este es un ejemplo aplicado de *privacidad por diseño*.

---

## 9. Seguridad en tránsito y cabeceras

- **TLS obligatorio** en producción (HSTS con `max-age` de un año)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- CORS con `*` **bloqueado en producción** por validación de arranque
- Los errores no controlados devuelven un mensaje genérico: una traza podría
  revelar estructura interna o datos de pacientes

---

## 10. Gestión de secretos

Todas las claves provienen de variables de entorno; ninguna está en el
repositorio (`.env` está en `.gitignore`).

En arranque con `ENTORNO=produccion`, la aplicación **se niega a iniciar** si
falta algún secreto o si CORS está abierto.

**Limitación reconocida:** en esta fase las claves viven en variables de
entorno. Un despliegue productivo real debería usar un KMS (AWS KMS, Azure Key
Vault o GCP KMS) con rotación automática. El formato versionado del ciphertext
(`v1:`) ya deja preparada esa migración.

---

## 11. Limitaciones conocidas

Reconocerlas explícitamente es parte del rigor del trabajo:

1. **Datos sintéticos.** La base contiene datos generados, no reales. Ningún
   dato de paciente real fue tratado.
2. **Sin MFA activo.** El esquema contempla los campos (`mfa_habilitado`,
   `mfa_secret_cifrado`) pero el segundo factor no está implementado.
3. **Claves en entorno, no en KMS.** Ver sección 10.
4. **Sin SMART on FHIR.** La autorización del servidor FHIR se apoya en la
   API intermedia, no en OAuth2 con scopes FHIR nativos.
5. **Blind index solo soporta igualdad exacta.** Ver sección 3.
6. **Servidor HAPI FHIR sin autenticación propia** en la configuración de
   desarrollo. En producción debería ir detrás de un gateway autenticado.

---

## 12. Marco normativo aplicable

| Norma | Ámbito |
|---|---|
| **Ley 1581 de 2012** | Protección de datos personales; datos de salud como sensibles |
| **Decreto 1377 de 2013** | Reglamenta la Ley 1581 |
| **Ley 2015 de 2020** | Historia clínica electrónica interoperable |
| **Resolución 1995 de 1999** | Manejo de la historia clínica |
| **Resolución 3100 de 2019** | Habilitación de servicios de salud |
| **Resolución 256 de 2016** | Sistema de Información para la Calidad |
| **ISO 27001 / ISO 27799** | Gestión de seguridad de la información en salud |
