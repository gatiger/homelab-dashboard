# Upgrade from v0.3 to v0.4

1. Keep the existing `dashboard-data` Docker volume. Do not use `docker compose down -v`.
2. Replace the backend and frontend source folders with the v0.4 folders.
3. Update the Compose stack to add the `socket-proxy` service and internal `docker-api` network from the v0.4 `docker-compose.yml`.
4. Keep your existing published dashboard port (for example `8082:80`).
5. Rebuild and recreate the stack: `docker compose up -d --build --force-recreate`.
6. Hard-refresh the browser after the new frontend starts.

The database migration is automatic. Existing administrator accounts and cards are preserved.
