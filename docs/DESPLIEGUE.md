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

## 3. Migraciones del Corte 2 (base compartida)

Solo Carlos las aplica, en orden, después de revisarlas:

```bash
python scripts/aplicar_sql.py db/08_roles_corte2.sql
python scripts/aplicar_sql.py db/09_perfiles.sql
python scripts/aplicar_sql.py db/10_remisiones.sql
python scripts/aplicar_sql.py db/11_areas_traslados.sql
python scripts/aplicar_sql.py db/12_turnos.sql
python scripts/aplicar_sql.py db/13_notificaciones.sql
python scripts/corregir_nombres.py        # nombres que no coincidían con el sexo
```

`13` crea la bandeja de notificaciones, las alertas críticas (`alertas_criticas`,
distinta de la tabla `alertas` del Corte 1) y el registro de eventos FHIR del
sistema reactivo (R17 a R21; ver `docs/EVENTOS.md`). Para R21 el `.env` debe
tener `HOOK_SECRET` (el secreto que HAPI manda en la cabecera del rest-hook);
sin él la Subscription no se registra y el receptor rechaza todo.

`10` crea la tabla de remisiones (R08) y sus permisos: el médico remite, el
especialista la ve, puede revisar al paciente y la acepta o la rechaza con un
motivo, y luego la cierra como atendida. Agrega `cerrada_at`/`cerrada_por`:
al rechazar, el especialista pierde el acceso a la ficha; al atender, lo
conserva `REMISION_ACCESO_DIAS` (7). Se puede correr más de una vez, también
sobre una base que ya tenía la versión anterior de la tabla.

`12` crea los turnos de enfermería jefe por área (mañana 07-13 y tarde 13-19
de 6 h, noche 19-07 de 12 h) con tres jefes que rotan por área (`jefe_urg`,
`jefe_urg2`, `jefe_urg3`, y lo mismo para uci, ucip, piso4 y piso5). Solo el
jefe de turno opera el área; los demás la ven en solo lectura y pueden
"cubrir el turno" con motivo. Correrla otra vez regenera la programación desde
ayer hasta dentro de 14 días (hay que hacerlo antes de que se acabe).

`11` organiza las camas por área: cada enfermero(a) jefe tiene un área a cargo
(cuentas `jefe_urg`, `jefe_uci`, `jefe_ucip`, `jefe_piso4`, `jefe_piso5`; `jefe01`
queda en Cirugía) y solo asigna camas de su área. Crea la tabla `traslados`
(el área origen pide, el área destino acepta eligiendo cama o rechaza con
motivo) y el permiso de alta para médico y especialista: el alta la da el
médico tratante con tipo de egreso y motivo, y la cama queda en proceso de
alta hasta que enfermería confirma la salida. Se puede correr más de una vez.

`08` crea los roles `medico`, `especialista` y `contable` y las cuentas
`medico01`, `especialista01`, `contable01` y `bloqueo_prueba` (misma contraseña
de demostración que `admin`). Se puede correr más de una vez.

`09` deja los perfiles definitivos, sin duplicados: las cuentas de
`medico_general`, `medico_especialista` y `facturacion` pasan a `medico`,
`especialista` y `contable`; `director_medico` pasa a ser `coordinador`
(coordinador del hospital: tablero general, sin pacientes) y la coordinación
quirúrgica queda en `enfermero_jefe` (cuenta de demostración `jefe01`). Médico
y especialista ven solo sus pacientes. Cierra las sesiones abiertas para que
todos entren con su perfil nuevo. Se puede correr más de una vez.

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

El volumen nuevo ya trae el esquema (`01`) y los catálogos (`02`). Faltan los
datos, que se cargan desde este equipo por el puerto `5433`:

```bash
# En el .env, temporalmente, para los scripts que corren fuera de Docker:
# DATABASE_URL=postgresql+psycopg2://hsr:<POSTGRES_PASSWORD>@localhost:5433/hsanrafael
python scripts/generar_datos.py --meses 6 --pacientes 4000
python scripts/aplicar_sql.py db/03_datos_sinteticos.sql
python scripts/aplicar_sql.py db/04_mejoras_catalogo_eventos.sql
python scripts/aplicar_sql.py db/06_permisos_imagen.sql
python scripts/aplicar_sql.py db/07_tipo_documento_por_edad.sql
python scripts/aplicar_sql.py db/08_roles_corte2.sql
python scripts/aplicar_sql.py db/09_perfiles.sql
python scripts/aplicar_sql.py db/10_remisiones.sql
python scripts/aplicar_sql.py db/13_notificaciones.sql
```

`05_cedula_como_llave.sql` **no** se aplica: era la migración de una base
antigua y `01_schema.sql` ya trae ese cambio.

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
