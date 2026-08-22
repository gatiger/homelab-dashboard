# Install on Synology DSM (Container Manager)

Synology Container Manager supports multi-container **Projects** backed by Docker Compose, and v0.7 can also run as a single image.

## Project method

1. Open **Container Manager > Project > Create**.
2. Choose a project name and working directory.
3. Upload the repository's `compose.yaml` or paste it into the editor.
4. Deploy/start the project.
5. Open the NAS address on port 8080 (or your configured port).

For easier NAS backups, you may replace the named volume with a bind mount such as `/volume1/docker/homelab-dashboard:/app/data`.

**Caution:** Synology's Project **Clean** action corresponds to `docker-compose down` and its documentation states it can remove project volumes. Back up `/app/data` before destructive project operations.

Official Synology reference:
- https://kb.synology.com/en-us/DSM/help/ContainerManager/docker_project
