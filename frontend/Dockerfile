# Web compilada con Vite y servida por nginx, que reenvía a la API sus rutas
# (las mismas que el proxy de vite.config.ts).

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_NTFY_TOPIC
RUN npm run build


FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
