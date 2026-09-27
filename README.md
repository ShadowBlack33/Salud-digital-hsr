# Sistema de Coordinación de Capacidad Quirúrgica

**Hospital San Rafael** (caso hipotético · ~300 camas · 13 quirófanos)
Proyecto integrador — Sistemas en Salud Digital

Coordinación en tiempo real de quirófanos, camas y urgencias, con
interoperabilidad HL7 FHIR R4.

---

## Estado

| Componente | Estado |
|---|---|
| Modelo relacional PostgreSQL (24 tablas, 4 vistas) | Completo |
| Datos sintéticos calibrados con literatura | Completo |
| API FastAPI con Swagger | Completo |
| Autenticación JWT + refresh rotativo | Completo |
| RBAC granular (14 roles, 39 permisos) | Completo |
| Cifrado AES-256-GCM + blind index | Completo |
| Soft delete / soft edit / restauración | Completo |
| Auditoría append-only | Completo |
| Integración HL7 FHIR R4 | Completo |
| Vistas de caso de negocio | Completo |
| Pruebas end-to-end | 52/52 |

---

## Instalación

### 1. Dependencias

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Secretos

```bash
cp .env.example .env
```

Generar las tres claves:

```bash
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Una para `APP_ENCRYPTION_KEY`, otra distinta para `APP_BLIND_INDEX_KEY`, y
una tercera para `JWT_SECRET_KEY`.

> Las claves deben fijarse **antes** de generar los datos: los registros se
> cifran con ellas y no podrán descifrarse con otras.

### 3. Base de datos

```bash
psql "$DATABASE_URL" -f db/01_schema.sql
psql "$DATABASE_URL" -f db/02_seed_catalogos.sql
python scripts/generar_datos.py --meses 6 --pacientes 4000
psql "$DATABASE_URL" -f db/03_datos_sinteticos.sql
```

### 4. Servidor HAPI FHIR

```bash
docker compose up -d
# http://localhost:8080/fhir
```

### 5. API

```bash
uvicorn app.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs
```

### 6. Verificación

```bash
python scripts/test_e2e.py
```

---

## Exposición pública

```bash
cloudflared tunnel --url http://localhost:8000   # API
cloudflared tunnel --url http://localhost:8080   # HAPI FHIR
```

Comprobar desde **otra red** (datos móviles, no el wifi local) antes de la
demostración.

---

## Usuarios de prueba

Contraseña común: `Demo#Hospital2026`

| Usuario | Rol | Capacidad distintiva |
|---|---|---|
| `admin` | Administrador | Todo, incluida la restauración |
| `director` | Director médico | Lectura amplia + analítica |
| `coordinador` | Coordinador de quirófanos | Agenda y recursos, sin restaurar |
| `medi0001` | Médico especialista | Solo sus propios registros |
| `enfe0001` | Enfermero | Estado de camas y quirófanos |
| `secr0001` | Secretaria | Agenda, sin datos clínicos |
| `integracion_svc` | Servicio de integración | Solo sincronización FHIR |

---

## Estructura

```
db/
  01_schema.sql              Esquema completo
  02_seed_catalogos.sql      Roles, permisos y catálogos clínicos
  03_datos_sinteticos.sql    Generado, no versionado
app/
  core/
    crypto.py                AES-256-GCM y blind index
    security.py              Argon2id, JWT y motor RBAC
    config.py                Configuración
    deps.py                  Sesión de BD y guardas de permisos
  models/                    Modelos SQLAlchemy
  api/
    auth.py                  Login, refresh, logout
    pacientes.py             CRUD con cifrado y soft ops
    clinico.py               Encuentros y observaciones
    recursos.py              Camas, quirófanos, FHIR, auditoría, analítica
  services/
    auditoria.py             Auditoría y operaciones soft
    fhir.py                  Mapeo y cliente HAPI
scripts/
  generar_datos.py           Generador sintético
  test_e2e.py                Pruebas end-to-end
docs/
  SEGURIDAD.md               Justificación de seguridad
  MAPEO_FHIR.md              Mapeo BD → FHIR
```

---

## Guion de demostración (7 minutos)

**1. Autenticación y roles diferenciados** (1 min)
`POST /auth/login` con `admin` y con un médico. Comparar
`GET /auth/yo`: distinto rol, distinta lista de permisos.

**2. Autorización de dos niveles** (2 min)
- Médico A crea un paciente → `201`
- Médico B intenta editarlo → `403` *"solo sus propios registros"*
- Médico A lo edita → `200`
- `GET /pacientes/{id}/historial` → el valor anterior quedó registrado

**3. Soft delete y restauración** (1,5 min)
- Médico A borra su paciente → `200`
- `GET` del paciente → `404`
- En la base sigue existiendo con `activo = false`
- Médico intenta restaurar → `403`; coordinador → `403`; **admin** → `200`

**4. Cifrado** (1 min)
- `SELECT documento_cifrado FROM pacientes LIMIT 1` → `v1:...` ilegible
- `GET /pacientes/buscar?documento=...` → encuentra sin descifrar la tabla
  (blind index)

**5. Interoperabilidad FHIR** (1 min)
- `PATCH /camas/1/estado` con `en_limpieza`
- `GET /fhir/preview/cama/1` → `operationalStatus` = `H` (Housekeeping)
- `POST /fhir/sync/paciente/{id}` → el recurso aparece en HAPI
- `GET /fhir/buscar/Patient?_count=5`

**6. Caso de negocio y auditoría** (0,5 min)
- `GET /analitica/costo-ociosidad` → pérdida estimada en pesos
- `GET /auditoria` → toda la sesión anterior trazada, incluidos los intentos
  denegados

---

## Fundamento de los datos sintéticos

Las distribuciones están calibradas con literatura real, no elegidas al azar:

- **Cancelación 2,7 %–7,6 %** y 44 % por causas administrativas
  (Segnini et al., 2022)
- **Reparto de causas:** 56,7 % paciente, 40,5 % prestador, 2,7 % asegurador
  (Muñoz-Caicedo et al., 2019)
- **Duración quirúrgica log-normal:** una cirugía rara vez termina antes de lo
  previsto, pero puede alargarse mucho
- **Tipo de cama según procedimiento:** cardiovascular y neurocirugía → UCI
  (trabajo de campo)
- **Período de crisis** (agosto 2026) que satura la UCI, para probar el
  comportamiento del sistema bajo presión

> **Advertencia metodológica.** Los modelos predictivos que se entrenen sobre
> estos datos aprenderán los patrones que el generador introdujo. Sirven para
> validar el *pipeline*, no como evidencia de precisión. Con datos reales de
> la institución, la misma arquitectura permitiría entrenar un modelo
> productivo.

---

## Referencias

- Segnini, F. J., Domínguez-Torres, L. C., & Vega-Peña, N. (2022).
  Cancelación de procedimientos quirúrgicos electivos. *Iatreia*, 35(2), 175–182.
- Muñoz-Caicedo, A., Perlaza-Cuero, L. A., & Burbano-Álvarez, V. A. (2019).
  Causas de cancelación de cirugía programada en una clínica de alta
  complejidad de Popayán. *Rev. Fac. Med.*, 67(1), 17–21.
- HL7 FHIR R4 — https://hl7.org/fhir/R4/
- Ley 1581 de 2012 · Ley 2015 de 2020 · Resolución 3100 de 2019
