# Install on QNAP (Container Station)

QNAP Container Station supports applications defined with Docker Compose YAML.

## Compose application

1. Open **Container Station**.
2. Choose **Create > Create Application**.
3. Name the application `homelab-dashboard`.
4. Paste the contents of `compose.yaml` into the YAML editor.
5. Validate the YAML, then create the application.
6. Open the QNAP host address on port 8080 (or your configured port).

For easier backup, map a persistent QNAP share/folder to `/app/data` instead of relying on an opaque named volume.

Docker host statistics remain optional and are not required for normal dashboard operation.
