# Despliegue (Corte 2)

## 1. Levantar todo

```bash
cp .env.example .env          # y llenar los valores (canal privado del equipo)
docker compose up -d --build
docker compose ps             # todos deben quedar "running" / "healthy"
```

Servicios: `postgres`, `mongo`, `fhir-db`, `hapi-fhir`, `orthanc`, `ml`, `api`,
`front` (nginx) y `cloudflared`.

Al terminar de arrancar, el servicio `jornada` corre `scripts/simular_jornada.py` una vez
(cirugías en curso, camas ocupadas, tiempos al día) y se apaga: por eso aparece como
"Exited (0)" en `docker compose ps`, y está bien. Para repetirlo a mano:
`docker compose run --rm jornada`. Para no correrlo, `SIMULAR_JORNADA=false` en el `.env`.

## 2. URL pública

```bash
docker compose logs cloudflared | grep trycloudflare.com
```

Todo sale por esa única URL HTTPS:

| Ruta | Va a |
|---|---|
| `/` | el front |
| `/api/...` | la API (por ejemplo `/api/auth/login`, `/api/docs`) |
| `/api/eventos/...` | el canal en vivo (SSE, sin buffer) |
| `/fhir/...` | el servidor HAPI FHIR |

La URL de un *quick tunnel* cambia cada vez que el contenedor `cloudflared` se
reinicia. Se genera el sábado 17, se copia a `tester.yaml` y **no se reinicia
el contenedor** hasta después de la sustentación. El equipo que lo corre se
queda encendido del 19 al 20.

### URL fija (opcional, recomendado si hay dominio)

Un *quick tunnel* no necesita cuenta, pero su URL cambia al reiniciar. Un túnel
con nombre da una URL fija; necesita una cuenta de Cloudflare **y un dominio
administrado en Cloudflare** (puede ser uno barato).

1. En el panel de Cloudflare: **Zero Trust → Networks → Tunnels → Create a
   tunnel → Cloudflared**. Ponerle nombre (por ejemplo `hsr`).
2. Copiar el token que muestra el paso de instalación (lo que va después de
   `--token`).
3. En **Public Hostname**, agregar por ejemplo `hsr.tudominio.com` con
   servicio `HTTP` y URL `front:80`.
4. En el `.env`:

       CLOUDFLARED_COMANDO=tunnel --no-autoupdate run --token <el token>

5. `docker compose up -d cloudflared`. La URL fija es la del paso 3.

El token es un secreto: va solo en el `.env`.

## 3. Base de datos

Toda la estructura está en **un solo archivo**, `db/esquema_completo.sql`
(tablas, funciones, triggers, extensión `vector` del RAG y catálogos: roles,
permisos, especialidades, EPS, CIE-10, procedimientos, servicios). Es el
estado final de las migraciones 01 a 15, que quedan en `db/historial/` como
registro de cómo se llegó ahí (no se vuelven a aplicar).

Los datos de personas los genera `scripts/generar_datos.py`: personal,
pacientes, encuentros, eventos y las cuentas de demostración (`admin`,
`medico01`, `especialista01`, `contable01`, `bloqueo_prueba`, `jefe01`, los
jefes por área `jefe_urg`, `jefe_urg2`, `jefe_urg3`... y `paciente_demo`, todas
con la contraseña de demostración) con sus turnos de los próximos 14 días.

Base nueva (o reiniciada), en orden. En la base compartida solo lo hace Carlos:

```bash
python scripts/aplicar_sql.py db/esquema_completo.sql
python scripts/generar_datos.py --meses 6 --pacientes 4000     # escribe db/03_datos_sinteticos.sql
python scripts/aplicar_sql.py db/03_datos_sinteticos.sql
python scripts/rag_indexar.py                                  # guías del RAG
```

`generar_datos.py` cifra con las claves del `.env` (`APP_ENCRYPTION_KEY`,
`APP_BLIND_INDEX_KEY`): hay que generar con las mismas claves que usa la API.

Para regenerar solo los datos, sin tocar la estructura:
`python scripts/aplicar_sql.py db/00_reset_datos.sql` y los dos pasos de datos.
La programación de turnos de los jefes cubre de ayer a dentro de 14 días; para
extenderla, `python scripts/aplicar_sql.py db/historial/12_turnos.sql` (se puede
correr cuantas veces haga falta).

Un cambio nuevo de estructura va como migración numerada (`db/16_...sql`),
se aplica en la base compartida y luego se incorpora a `esquema_completo.sql`
(pg_dump de la base con todo aplicado, sin los datos de personas).

Para R21 el `.env` debe tener `HOOK_SECRET` (el secreto que HAPI manda en la
cabecera del rest-hook); sin él la Subscription no se registra y el receptor
rechaza todo. Las remisiones dan acceso a la ficha mientras están pendientes o
aceptadas y `REMISION_ACCESO_DIAS` (7) después de atendidas.

### Perfiles

| Perfil | Entra a | Ve |
|---|---|---|
| `admin` | Administración | Usuarios, bloqueos, auditoría, servicios, pacientes y facturación |
| `coordinador` | Hospital | Capacidad por área, riesgo de colapso, dinero, IA. Ningún paciente |
| `enfermero_jefe` | Cirugías | Programa, mueve y cancela cirugías; centro de mando; pacientes |
| `medico` | Mi turno | Sus pacientes, casos críticos, IA, remisiones |
| `especialista` | Remisiones | Sus pacientes y sus cirugías (si está asignado o no) |
| `contable` | Facturación | Cobros por tipo, estado, entidad y paciente. Nada clínico |
| `paciente` | Mi salud | Su información y lo que se le cobra a él y a su EPS |

### Datos de demostración

El contenedor `jornada` corre, al levantar el sistema, `simular_jornada.py`
(camas y quirófanos del momento), `casos_demo.py` (pacientes y casos críticos
de `medico01` y `especialista01`) y, una sola vez, `cargar_radiografias.py`
(radiografías reales del NIH ChestX-ray14 asignadas a pacientes, en el PACS).

## 4. Usar el PostgreSQL del compose en vez de Neon

El volumen nuevo ya trae `db/esquema_completo.sql`. Faltan los datos, que se
cargan desde este equipo por el puerto `5433`:

```bash
# En el .env, temporalmente, para los scripts que corren fuera de Docker:
# DATABASE_URL=postgresql+psycopg2://hsr:<POSTGRES_PASSWORD>@localhost:5433/hsanrafael
python scripts/generar_datos.py --meses 6 --pacientes 4000
python scripts/aplicar_sql.py db/03_datos_sinteticos.sql
python scripts/rag_indexar.py
```

Después, para la API dentro de Docker:

```
DATABASE_URL=postgresql+psycopg2://hsr:<POSTGRES_PASSWORD>@postgres:5432/hsanrafael
```

y `docker compose up -d api`.

## 5. Comprobaciones rápidas

```bash
URL=https://<la-url>.trycloudflare.com
curl -s $URL/api/salud
# Rate limiting (R03): una ráfaga debe recibir algunos 429
for i in $(seq 1 80); do curl -s -o /dev/null -w "%{http_code}\n" $URL/api/salud; done | sort | uniq -c
# CORS (R03): un origen desconocido no recibe Access-Control-Allow-Origin
curl -s -D - -o /dev/null -H "Origin: https://otro.example" $URL/api/salud | grep -i access-control || echo "sin CORS (bien)"
# FHIR: sin token solo se publica una Observation (R21) y se lee /metadata
curl -s -o /dev/null -w "%{http_code} (esperado 401)\n" "$URL/fhir/Patient?_count=1"
curl -s -o /dev/null -w "%{http_code} (esperado 200)\n" "$URL/fhir/metadata"
curl -s -o /dev/null -w "%{http_code} (esperado 403)\n" -X DELETE "$URL/fhir/Patient/1"
```

## 6. Interruptores y reglas configurables

| Variable (en `.env`) | Valor por defecto | Qué hace |
|---|---|---|
| `VITE_DATOS_DEMO` | `true` | `false` = el front no rellena con datos de ejemplo las rutas que aún no existen y oculta el panel de demostración. Para la sustentación, cuando todos los módulos estén desplegados. Requiere `docker compose build front`. El tester habla con la API: nunca ve esos datos. |
| `REMISION_ACCESO_DIAS` | `7` | Días que el especialista conserva acceso a la ficha después de cerrar una remisión como atendida. |
| `FRACCION_ALTAS_12H` | `0.7` | Supuesto del escenario de ocupación del coordinador: fracción de altas en proceso que se completan en 12 h. |

## 7. Qué depende de Neon

Con `DATABASE_URL` apuntando a Neon, la API y los scripts usan la base
compartida; todo lo demás (HAPI y su base, Orthanc, MongoDB, ml, nginx,
cloudflared) corre en el compose. Para una ejecución autónoma desde un clon
limpio, sin Neon, ver la sección 4: el PostgreSQL del compose recibe el
esquema, los catálogos, los datos sintéticos y las migraciones `04`–`10`.
