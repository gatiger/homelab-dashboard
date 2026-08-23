# Security Policy

Do not report vulnerabilities in public issues.

Until a private reporting address is established, use GitHub's private vulnerability reporting feature for the repository.

Sensitive values such as passwords, tokens, and API keys must never be committed. Stored integration secrets are encrypted at rest and integration requests originate from the backend rather than exposing saved credentials to the browser.

Live status checks are backend-originated requests to service URLs configured by an authenticated dashboard administrator. Public HTTPS targets require valid certificates. Private/local targets may use self-signed certificates for homelab compatibility.

## Theme packages

Imported themes are treated as untrusted data. The supported theme package format accepts only validated metadata and six-digit hexadecimal design tokens. Theme packages cannot contain executable JavaScript, arbitrary CSS, remote resource URLs, Docker permissions, filesystem access, or access to stored service credentials.


## Integration secrets

Stored service API keys and qBittorrent WebUI credentials are encrypted using the local key in `/app/data/secret.key`. They are not returned through service configuration responses after storage. Back up the SQLite database and `secret.key` together.


## Update Manager / Docker agent

v0.12 keeps Docker write privileges out of the main dashboard container. The optional update-agent does mount the Docker socket and should therefore be treated as a privileged host-management component. Its HTTP API is placed only on an internal Compose network, can require a shared token, accepts provider-specific resource identifiers rather than shell commands, and only exposes Compose projects whose working/config paths resolve inside the configured `UPDATE_AGENT_STACKS_ROOT`. Mount that stacks root read-only and never publish the agent port to the LAN or Internet.

TrueNAS updates are sent to TrueNAS itself through its authenticated JSON-RPC WebSocket API. Use HTTPS/WSS and a dedicated user-linked API key with only the roles needed for app discovery/upgrades.
