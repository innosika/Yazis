# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
# `npm ci` when a lockfile is present (reproducible), `npm install` on first build.
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY tsconfig.json vite.config.ts eslint.config.js index.html ./
COPY src ./src
# The only automated gate the frontend has: type-check, lint and unit-test before building.
RUN npm run typecheck && npm run lint && npm run test && npm run build

FROM nginx:1.27-alpine AS runtime
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/irs.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/index.html >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
