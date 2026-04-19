FROM nginx:1.27-alpine

# Install certbot + openssl
RUN apk add --no-cache certbot openssl bash

# Create directories
RUN mkdir -p /var/www/certbot /etc/nginx/certs

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Startup script
COPY docker-entrypoint-nginx.sh /docker-entrypoint-nginx.sh
RUN chmod +x /docker-entrypoint-nginx.sh

EXPOSE 80 443

ENTRYPOINT ["/docker-entrypoint-nginx.sh"]
