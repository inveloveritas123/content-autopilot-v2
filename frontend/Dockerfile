FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist/ /usr/share/nginx/html/

# nginx:alpine-Image hat bereits den 'nginx'-User (uid 101).
# Port 8080 (>1024) erlaubt non-root Binding ohne NET_BIND_SERVICE.
# USER nginx — disabled: needs tmpfs for /var/cache/nginx (followup)
