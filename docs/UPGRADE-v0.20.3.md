# Upgrade to v0.20.3

v0.20.3 adds an optional backend-only Internal / monitoring URL to service cards.

## Database migration

The Dashboard automatically adds a nullable `internal_url` column to existing service records. No manual database command is required.

## Existing cards

Existing cards continue using their Browser URL for both launching and backend monitoring until an Internal / monitoring URL is entered.

For a service whose friendly/Tailscale/reverse-proxy URL is not reachable from the Dashboard container:

1. Edit the service card.
2. Leave **Browser URL** unchanged.
3. Enter a backend-reachable LAN or Docker address under **Internal / monitoring URL**.
4. Save the card.
5. Refresh service status and confirm the card reports Online.

Example:

```text
Browser URL:               http://services.example.com:8989
Internal / monitoring URL: http://192.168.1.20:8989
```

If split DNS or Docker `extra_hosts` already makes the Browser URL resolve correctly inside the Dashboard container, leave the internal field blank.

No Compose, environment-variable, credential, or management-provider change is required for the application upgrade itself.
