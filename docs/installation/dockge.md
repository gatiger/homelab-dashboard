# Install with Dockge

Dockge is a convenient Compose UI, but it is not required by Homelab Dashboard.

## Requirements

- A working Dockge installation.
- Access to create a new Compose stack.
- An unused host port (8080 by default).

## Recommended install

1. Create a new Dockge stack named `homelab-dashboard`.
2. Paste the repository's `compose.yaml` into the stack editor.
3. If port 8080 is already in use, change `${DASHBOARD_PORT:-8080}` to another host port or add `DASHBOARD_PORT` in the stack environment.
4. Start the stack.
5. Open `http://SERVER-IP:PORT` and create the first administrator account.

Because the production Compose file uses the published GHCR image, Dockge no longer needs the repository's `backend` or `frontend` source folders.

## Enable Docker host insight

Dockge can merge the base Compose file with `compose.docker.yaml` when both files are available. If your Dockge workflow only uses one Compose editor, copy the `socket-proxy` service, `DOCKER_PROXY_URL`, and `docker-api` network sections from `compose.docker.yaml` into the stack.

Docker insight is optional. A Dockge card still works as a normal monitored link without it.

## Updating

Pull/recreate the stack using the same Compose configuration. Do not remove the `homelab-dashboard-data` volume.

## Optional v0.12 one-click updates

Homelab Dashboard can update Compose/Dockge-managed services without opening Dockge, but this is deliberately opt-in because it requires Docker write privileges.

Add the `update-agent` service/network from `compose.management.yaml` to the dashboard stack (or launch the base + management overlay outside Dockge). Set:

```env
UPDATE_AGENT_TOKEN=<long-random-token>
UPDATE_AGENT_STACKS_ROOT=<absolute host path to Dockge's stacks directory>
```

The stacks directory is mounted read-only into the update agent. Dockge's internal `/opt/stacks/...` labels are mapped back to the configured host stack directory when necessary. The Docker socket is mounted only into the update agent. Do **not** publish port `8765`; the dashboard reaches it through the internal `update-api` network.

After the agent is healthy, edit a dashboard card, choose **Managed by → Docker Compose / Dockge**, and select the discovered stack/service.
