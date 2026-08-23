FROM python:3.13-alpine
ARG VERSION=dev
LABEL org.opencontainers.image.title="Homelab Dashboard Update Agent" \
      org.opencontainers.image.description="Restricted Docker Compose update agent for Homelab Dashboard" \
      org.opencontainers.image.source="https://github.com/gatiger/homelab-dashboard" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${VERSION}"

WORKDIR /app
RUN apk add --no-cache docker-cli docker-cli-compose && \
    python -m pip install --no-cache-dir fastapi==0.116.1 uvicorn==0.35.0 pydantic==2.11.7
COPY agent/app.py /app/app.py
USER root
EXPOSE 8765
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8765"]
