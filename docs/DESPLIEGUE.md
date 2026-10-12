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
```

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
```
