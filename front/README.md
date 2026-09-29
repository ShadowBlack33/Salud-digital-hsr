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
| `VITE_API_BASE` | URL de la API, vista desde el navegador. Debe ser `http://localhost:8000`, no `host.docker.internal`. |
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
