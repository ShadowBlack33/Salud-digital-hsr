# En producción React no corre Node: "npm run build" genera HTML/CSS/JS
# estático y eso es lo único que sirve nginx.
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# Vite incrusta estas variables en el JS al compilar: para cambiarlas hay que
# reconstruir la imagen (docker compose build --no-cache front).
#   VITE_API_BASE          URL de la API, vista desde el NAVEGADOR (no desde el contenedor).
#   VITE_DEMO_PASSWORD     opcional: si se define, las cuentas de demostración del login
#                          rellenan también la contraseña. Queda visible en el JS
#                          publicado: úsala solo con datos sintéticos y en la demo.
#   VITE_OCULTAR_CUENTAS_DEMO=true  oculta por completo el bloque de cuentas de demostración.
ARG VITE_API_BASE=http://localhost:8000
ARG VITE_DEMO_PASSWORD=
ARG VITE_OCULTAR_CUENTAS_DEMO=false
ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_DEMO_PASSWORD=$VITE_DEMO_PASSWORD \
    VITE_OCULTAR_CUENTAS_DEMO=$VITE_OCULTAR_CUENTAS_DEMO
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
