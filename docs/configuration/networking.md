# Networking and remote access

Homelab Dashboard has two different network roles:

1. **The user's browser** opens a service when its card is clicked.
2. **The Dashboard backend** performs health checks and calls service APIs.

Those two requests do not have to use the same network path.

## Browser URL vs Internal / monitoring URL

Each service card has a required **Browser URL** and an optional **Internal / monitoring URL**.

Example:

```text
Browser URL:              https://sonarr.example.com
Internal / monitoring URL: http://192.168.1.20:8989
```

The Browser URL is returned to the frontend and used only when someone opens the card. The Internal / monitoring URL is used server-side for Online/Offline checks and supported rich integrations. If the internal field is blank, Dashboard uses the Browser URL for both purposes, preserving pre-v0.20.3 behavior.

Good internal targets include:

- a direct LAN address and port, such as `http://192.168.1.20:8989`;
- a Docker DNS/service name reachable from the Dashboard container, such as `http://sonarr:8989`;
- another private management address that is routable from the Dashboard container.

Do not expose a service port publicly just to make Dashboard monitoring work.

## Preferred single-hostname design: split DNS

When possible, keep one friendly hostname and make local DNS resolve it to the local service path while remote clients use the remote-access path.

Example:

```text
Inside the homelab: sonarr.example.com -> 192.168.1.20
Remote/Tailscale:   sonarr.example.com -> 100.x.y.z
```

With working split DNS, the Browser URL can also be the monitoring URL and the optional Internal / monitoring URL can stay blank.

## Docker `extra_hosts` override

If changing LAN DNS is not practical, Docker can override a hostname only for the Dashboard container.

Example Compose fragment:

```yaml
services:
  dashboard:
    extra_hosts:
      - "services.example.com:192.168.1.20"
```

After recreating the container, verify the result:

```bash
docker exec <dashboard-container> getent hosts services.example.com
```

This override changes only the Dashboard container's name resolution. It does not publish ports or change how phones/laptops resolve the hostname.

## Tailscale and other private overlays

Tailscale is a good way to access a homelab remotely without forwarding individual service ports to the public Internet. However, local Dashboard monitoring should not unnecessarily depend on Tailscale when Dashboard and the monitored service are already on the same LAN/host.

Recommended pattern:

```text
Remote phone/laptop -> Tailscale -> homelab service
Dashboard backend   -> LAN/Docker network -> homelab service
```

That way a Tailscale outage can affect remote access without causing healthy local services to appear Offline in Dashboard.

## Troubleshooting a false Offline state

First test the saved Browser URL from inside the Dashboard container. Then test the direct LAN/container address.

```bash
docker exec <dashboard-container> getent hosts service.example.com
```

```bash
docker exec -i <dashboard-container> python - <<'PY'
import urllib.request
for url in [
    "https://service.example.com/",
    "http://192.168.1.20:8989/",
]:
    try:
        response = urllib.request.urlopen(url, timeout=4)
        print(url, "->", response.status)
    except Exception as exc:
        print(url, "->", repr(exc))
PY
```

If the friendly/remote URL times out but the LAN address succeeds, either:

- fix local/split DNS;
- add a Docker `extra_hosts` override; or
- enter the working LAN/container address as the service's Internal / monitoring URL.

## Security notes

- Prefer private VPN/overlay access (for example Tailscale) over public port forwarding for administrative homelab services.
- An Internal / monitoring URL is not a security boundary. The Dashboard backend must already be trusted to reach the service and use any credentials saved for its integration.
- Avoid creating public DNS/port-forwarding rules solely to make backend monitoring work.
