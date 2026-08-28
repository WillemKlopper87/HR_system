# Sentech HCM frontend — static SPA build served by nginx, which also proxies
# /api and /admin to the Django backend so the browser sees one origin
# (ADR-005 single-host reverse-proxy shape; same as vite.config.ts in dev).
# Both pinned by digest for reproducible/supply-chain-traceable builds
# (HR_Code_report.md lower-priority note) -- re-pull deliberately
# (`docker pull <image> && docker inspect --format='{{index .RepoDigests 0}}'
# <image>`) to take a new version, not by editing the tag alone.
FROM node:lts-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
