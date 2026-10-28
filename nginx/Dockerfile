FROM node:22-alpine AS frontend-builder

WORKDIR /build/system-ui

COPY system-ui/package.json system-ui/package-lock.json ./
RUN npm ci

COPY system-ui/ ./
RUN npm run build

FROM nginx:1.27-alpine

RUN apk upgrade --no-cache \
    && apk add --no-cache certbot openssl bash \
    && mkdir -p /var/www/certbot /etc/nginx/certs

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/docker-entrypoint-nginx.sh /docker-entrypoint-nginx.sh
COPY --from=frontend-builder /build/system-ui/dist/ /usr/share/nginx/html/
RUN tr -d '\r' < /docker-entrypoint-nginx.sh > /tmp/docker-entrypoint-nginx.sh \
    && mv /tmp/docker-entrypoint-nginx.sh /docker-entrypoint-nginx.sh \
    && chmod +x /docker-entrypoint-nginx.sh

EXPOSE 80 443

ENTRYPOINT ["/docker-entrypoint-nginx.sh"]
