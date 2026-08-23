# Service integrations

Homelab Dashboard cards always work as normal monitored links. The integrations below are optional and add richer read-only information when credentials are configured.

## Supported in v0.11

| Service | Authentication used by dashboard | Rich information |
|---|---|---|
| Jellyfin | API key | Version and active sessions |
| Sonarr | API key | Health, queue, item progress, ETA when supplied, upcoming 7-day activity |
| Radarr | API key | Health, queue, item progress, ETA when supplied, upcoming 7-day activity |
| Prowlarr | API key | Version, health warnings, enabled indexer count |
| qBittorrent | WebUI username/password | Version, active/queued downloads, per-torrent progress/speed/ETA, global download speed |
| SABnzbd | API key | Queue, item progress, queue speed, ETA |
| Immich | API key | Server version and server statistics when the key has permission |
| TrueNAS | API key | Pool health/capacity and active scrub/resilver/expansion progress |
| Dockge / Docker Host | Optional restricted Docker socket proxy | Stack/container overview |

Stored API keys and qBittorrent credentials are encrypted in `/app/data` and are not returned to the browser after storage. Back up the database and `secret.key` together.

## Progress behavior

Adapters translate native service responses into the dashboard's shared activity model. A standard or wide card shows the highest-priority/current activity with:

- operation and item/job name
- progress bar and percentage when measurable
- transferred/total size when available
- transfer speed when available
- ETA when available
- a count when additional activities exist

Compact cards intentionally hide rich insight content to remain compact.

## Sonarr, Radarr, and Prowlarr

Copy the API key from the application's security/general settings and paste it into the card's Service Configuration dialog. The dashboard sends it only from the backend using the service's API-key header.

The current adapters target Sonarr/Radarr API v3 and Prowlarr API v1.

## qBittorrent

Enter the same username and password used for the qBittorrent WebUI. Homelab Dashboard logs in through qBittorrent's WebUI API and uses the returned session cookie only for that telemetry request. The password is not exposed to the browser after saving.

## SABnzbd

Enter the SABnzbd API key. The integration uses the read-only queue API to report current downloads and transfer state.

## Immich

Create an Immich API key with sufficient permission to read server information/statistics. If the server-about endpoint succeeds but statistics permission is unavailable, the card remains connected and notes that detailed statistics are unavailable.

## TrueNAS compatibility note

v0.11 prefers the current versioned JSON-RPC WebSocket API (`/api/current`) for TrueNAS telemetry and management. The older REST v2 path remains only as a read-only telemetry fallback for older installations; it is not used for TrueNAS App upgrades.

For app management, use an HTTPS TrueNAS card URL plus an API key. Saving the API-key owner username is recommended for current user-linked key authentication and future compatibility. Use a dedicated, least-privileged TrueNAS account/key that has only the roles needed for the telemetry and app-management operations you intend to allow.
