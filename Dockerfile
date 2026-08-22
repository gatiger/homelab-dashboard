# syntax=docker/dockerfile:1
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./

# Bundle the dashboard icon subset at image build time. Failure to fetch an
# individual icon does not fail the application build; the UI has a fallback.
RUN mkdir -p public/icons && \
    if [ -f icon-slugs.txt ]; then \
      while IFS= read -r icon; do \
        [ -z "$icon" ] && continue; \
        svg="public/icons/${icon}.svg"; \
        png="public/icons/${icon}.png"; \
        if [ ! -s "$svg" ] && [ ! -s "$png" ]; then \
          wget -q -O "$svg" "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/refs/heads/main/svg/${icon}.svg" || { \
            rm -f "$svg"; \
            wget -q -O "$png" "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/refs/heads/main/png/${icon}.png" || { rm -f "$png"; echo "Icon unavailable: $icon"; }; \
          }; \
        fi; \
      done < icon-slugs.txt; \
    fi
RUN npm run build

FROM python:3.13-slim AS runtime
ARG VERSION=dev
LABEL org.opencontainers.image.title="Homelab Dashboard" \
      org.opencontainers.image.description="A configurable self-hosted dashboard and control center for homelab services" \
      org.opencontainers.image.source="https://github.com/gatiger/homelab-dashboard" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/sites-available/default
COPY deploy/supervisord.conf /etc/supervisor/conf.d/homelab-dashboard.conf

RUN mkdir -p /app/data /run/nginx && \
    rm -f /etc/nginx/conf.d/default.conf

VOLUME ["/app/data"]
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1/api/health', timeout=3).read()" || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
