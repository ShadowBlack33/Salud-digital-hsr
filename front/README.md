# San Rafael OS · front

React 19 + Vite + Tailwind 4 + Lucide, con la paleta y los tokens de Bevel.

## Correrlo

    docker compose up -d --build front        # desde la carpeta del proyecto
    # http://localhost:5173

Para desarrollo sin Docker (necesita la API en el puerto 8000):

    cd front
    npm install
    npm run dev

## Variables (se fijan al compilar)

| Variable | Para qué |
|---|---|
| `VITE_API_BASE` | URL de la API vista desde el navegador. En Docker es `/api` (nginx hace de proxy, mismo origen). Con `npm run dev`, `http://localhost:8000`. |
| `VITE_DEMO_PASSWORD` | Opcional. Rellena también la contraseña al tocar una cuenta de demostración. Queda visible en el JS. |
| `VITE_OCULTAR_CUENTAS_DEMO` | `true` oculta el bloque de cuentas de demostración. |

Cambiar cualquiera exige reconstruir: `docker compose build --no-cache front`.

## Estructura

    src/api.js              cliente de la API (renueva el token solo)
    src/lib/                estados y semáforo, formato, hooks, cálculos del tablero
    src/components/         insignia, anillo, panel lateral, tarjeta de cama, cronograma de quirófanos, visor de imágenes
    src/pages/              Landing, Login
    src/pages/app/          Shell, Comando (centro de mando), Pacientes, Ficha
    src/index.css           tokens (Bevel + derivados de accesibilidad) y animaciones

## Decisiones

- El semáforo tiene cuatro grupos (disponible, ocupado, en proceso, bloqueado) sobre los 8 estados de cama y 5 de quirófano de la base. Siempre lleva color, ícono y texto.
- Los colores de datos de Bevel (verde, dorado, coral) son demasiado claros como texto (contraste 1,5–2,1). Sirven de relleno; el texto usa tonos oscuros derivados, definidos en `index.css`.
- El menú y las acciones se adaptan a los permisos que devuelve `/auth/yo`.
- El tablero consulta la API cada 15 s y se pausa con la pestaña oculta.
- Todo lo del tablero depende de que haya una jornada en curso: si la base solo tiene historia, corre `python scripts/simular_jornada.py`.

## Corte 2: pantallas por rol

Cada rol entra a su propia pantalla (`src/lib/roles.js`):

| Rol | Inicio | Además |
|---|---|---|
| `admin` | `/app/admin`: usuarios, cuentas bloqueadas, auditoría, servicios | Centro de mando, pacientes |
| `medico` | `/app/turno`: pendientes en vivo y sus pacientes | Remisiones, centro de mando, pacientes |
| `especialista` | `/app/remisiones`: remisiones recibidas | Centro de mando, pacientes |
| `contable` | `/app/facturacion` | Nada clínico |
| `paciente` | `/app/mi-salud` (pensada para celular) | Solo su información |
| Roles del Corte 1 | `/app/mando` (centro de mando) | Pacientes |

La ficha del paciente suma las pestañas **Análisis de IA** (aprobar o rechazar, ver el payload enviado al
modelo), **Remitir** y el botón de **historia clínica en PDF**. Arriba de todo quedan la campana con la
bandeja y las alertas críticas, que no se cierran hasta reconocerlas con una nota.

### Canal en vivo

`src/lib/tiempoReal.jsx` abre `EventSource(/eventos/stream?token=...)`. Cada evento recarga bandeja,
contadores y alertas, y avisa a las pantallas suscritas (`useEventos`). Sin sondeo.

### Rutas que todavía no existen

`src/lib/servicios.js` llama a la API real. Si la ruta aún no existe (404 "Not Found" genérico de
FastAPI) usa los datos de `src/lib/mocks.js` y la pantalla muestra **Datos de demostración**. Cuando
el equipo publica la ruta, se usa sola. Rutas que el front espera, además de las del contrato:

- `GET /ia/reportes?paciente_id=` lista los reportes de un paciente (todos los estados).
- `GET /ia/reportes?estado=pendiente` los reportes por revisar (para "Mi turno").
- `GET /especialistas` devuelve `[{id, nombre, especialidad}]` para el selector de remisión.
- Opcional en cada alerta: `escala_en` (ISO) y `escalada_at`, para la cuenta regresiva del escalamiento.
  Sin ellos, el front cuenta `VITE_MINUTOS_ESCALAMIENTO` (5 por defecto) desde `created_at`.

### Atajos

| Atajo | Qué hace |
|---|---|
| **Ctrl + K** | Buscar paciente: por nombre, o por documento completo con el índice ciego. |
| **Ctrl + Shift + D** | Panel de demostración: guion de los 6 pasos (se marcan solos) y eventos simulados. No cambia de rol ni da permisos. |

### Otras piezas

- **Cambio de contraseña** (`/cambiar-clave`): obligatorio cuando el admin crea la cuenta; también desde el chip del usuario.
- **En vivo:** indicador en la barra, contador de no leídas en el título de la pestaña, sonido y aviso del
  escritorio para alertas críticas (se activan desde la bandeja).
- **Errores:** 403 y 404 amables, aviso si se cae la conexión y un límite que evita la pantalla en blanco.
- **Carga diferida:** cada pantalla se descarga solo cuando se abre.

### Ensayo automático

`scripts/demo_e2e.py` abre médico, especialista, contable y admin a la vez y comprueba que cada reacción
llega sin recargar:

    python scripts/demo_e2e.py --url http://localhost:5173              # con eventos simulados
    python scripts/demo_e2e.py --url https://xxxx.trycloudflare.com --modo real --ver
