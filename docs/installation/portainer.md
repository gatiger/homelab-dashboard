# Install with Portainer

Portainer supports stacks from its web editor, an uploaded Compose file, or a Git repository.

## Web editor / upload

1. Open **Stacks > Add stack**.
2. Name the stack `homelab-dashboard`.
3. Choose **Web editor** and paste `compose.yaml`, or choose **Upload** and upload it.
4. Add environment variables such as `DASHBOARD_PORT` if you want to override defaults.
5. Deploy the stack.
6. Open `http://SERVER-IP:8080` (or the configured port).

## Git deployment

Repository: `https://github.com/gatiger/homelab-dashboard`  
Compose path: `compose.yaml`

Portainer can also use additional Compose paths. Add `compose.docker.yaml` only if you want the optional local Docker insight integration.

Official Portainer reference:
- https://docs.portainer.io/2.33-lts/user/docker/stacks/add
