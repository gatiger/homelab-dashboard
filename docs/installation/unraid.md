# Install on Unraid

Unraid does not natively use Docker Compose for its normal Docker UI, so the v0.7 all-in-one image is designed to work as a single standard container.

## Manual container

In the Unraid Docker UI, add a container with:

- **Repository:** `ghcr.io/gatiger/homelab-dashboard:latest`
- **Web UI / host port:** choose an unused host port such as `8080`
- **Container port:** `80/tcp`
- **Persistent host path:** `/mnt/user/appdata/homelab-dashboard`
- **Container path:** `/app/data`

Optional environment variables:

- `APP_NAME=Homelab Dashboard`
- `SESSION_HOURS=168`
- `COOKIE_SECURE=false`
- `STATUS_TIMEOUT=4`
- `STATUS_WORKERS=8`

Open `http://UNRAID-IP:8080` and complete first-run setup.

The normal install does not need Docker socket access. An Unraid Community Applications template is planned for a future release.

Official Unraid documentation notes that Docker Compose is not native to Unraid's standard Docker workflow:
- https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/overview/
