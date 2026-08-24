FROM node:20-alpine AS build

WORKDIR /app

# Lockfile is copied so `npm ci` installs the exact resolved tree. The previous
# `COPY package.json` + `npm install` re-resolved the caret ranges on every build,
# so the image that shipped was not the tree that was tested.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# CRA inlines env vars at build time. Default to the same-origin /api path served
# by nginx; override at build time to point a dev build at a backend directly.
ARG REACT_APP_API_BASE=/api
ENV REACT_APP_API_BASE=$REACT_APP_API_BASE
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    # 127.0.0.1, not localhost: busybox wget tries ::1 first.
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
