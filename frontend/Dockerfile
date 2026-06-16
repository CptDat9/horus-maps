# Build the Vite/React bundle, then serve it with nginx which also reverse-proxies
# /api and /ws to the backend (same-origin → no CORS; the app calls relative "/api",
# see src/services/api.ts, so no build-time API URL is needed).
FROM node:20-alpine AS build
WORKDIR /app
# `npm install` (not `npm ci`): the committed lock file is out of sync with
# package.json, and ci requires an exact match. install reconciles it — fine for
# a local/demo build.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
