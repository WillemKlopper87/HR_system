# Sentech HCM frontend — static SPA build served by nginx, which also proxies
# /api and /admin to the Django backend so the browser sees one origin
# (ADR-005 single-host reverse-proxy shape; same as vite.config.ts in dev).
FROM node:lts-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
