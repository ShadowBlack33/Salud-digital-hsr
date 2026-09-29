# En producción React no corre Node -- "npm run build" genera HTML/CSS/JS
# estático, y eso es lo único que termina sirviendo nginx. Por eso el patrón
# es casi idéntico al que ya usa el profesor para el front en HTML plano:
# nginx leyendo una carpeta. Solo que aquí esa carpeta la genera el build.
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# La URL de la API queda fija DENTRO del build (Vite la incrusta en el JS en
# tiempo de compilación, no se puede cambiar después sin reconstruir la imagen).
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
