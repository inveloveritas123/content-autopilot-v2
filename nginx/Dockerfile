FROM nginx:alpine
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/dist/ /usr/share/nginx/html/

# nginx:alpine-Image hat bereits den 'nginx'-User (uid 101).
# Port 8080 (>1024) erlaubt non-root Binding ohne NET_BIND_SERVICE.
# USER nginx — disabled: needs tmpfs for /var/cache/nginx (followup)
