export type CatalogEntry = {
  type: string;
  name: string;
  category: string;
  icon: string | null;
  defaultPort?: number;
  defaultScheme?: "http" | "https";
  description: string;
  aliases?: string[];
  integration?: "jellyfin" | "docker" | null;
};

export const SERVICE_CATALOG: CatalogEntry[] = [
  // Media management & streaming
  { type: "jellyfin", name: "Jellyfin", category: "Media", icon: "jellyfin", defaultPort: 8096, defaultScheme: "http", description: "Open-source media server", aliases: ["movies", "tv", "streaming"], integration: "jellyfin" },
  { type: "plex", name: "Plex", category: "Media", icon: "plex", defaultPort: 32400, defaultScheme: "http", description: "Media server and streaming platform", aliases: ["movies", "tv", "streaming"] },
  { type: "emby", name: "Emby", category: "Media", icon: "emby", defaultPort: 8096, defaultScheme: "http", description: "Personal media server", aliases: ["movies", "tv", "streaming"] },
  { type: "sonarr", name: "Sonarr", category: "Media", icon: "sonarr", defaultPort: 8989, defaultScheme: "http", description: "TV series management and automation", aliases: ["servarr", "tv"] },
  { type: "radarr", name: "Radarr", category: "Media", icon: "radarr", defaultPort: 7878, defaultScheme: "http", description: "Movie management and automation", aliases: ["servarr", "movies"] },
  { type: "lidarr", name: "Lidarr", category: "Media", icon: "lidarr", defaultPort: 8686, defaultScheme: "http", description: "Music collection management", aliases: ["servarr", "music"] },
  { type: "readarr", name: "Readarr", category: "Media", icon: "readarr", defaultPort: 8787, defaultScheme: "http", description: "Book and ebook management", aliases: ["servarr", "books"] },
  { type: "bazarr", name: "Bazarr", category: "Media", icon: "bazarr", defaultPort: 6767, defaultScheme: "http", description: "Subtitle management for Sonarr and Radarr", aliases: ["subtitles", "servarr"] },
  { type: "prowlarr", name: "Prowlarr", category: "Media", icon: "prowlarr", defaultPort: 9696, defaultScheme: "http", description: "Indexer manager and proxy", aliases: ["servarr", "indexers"] },
  { type: "overseerr", name: "Overseerr", category: "Media", icon: "overseerr", defaultPort: 5055, defaultScheme: "http", description: "Media request and discovery manager", aliases: ["requests", "plex"] },
  { type: "jellyseerr", name: "Jellyseerr", category: "Media", icon: "jellyseerr", defaultPort: 5055, defaultScheme: "http", description: "Media request manager for Jellyfin and Emby", aliases: ["requests", "jellyfin", "emby"] },
  { type: "seerr", name: "Seerr", category: "Media", icon: "seerr", defaultPort: 5055, defaultScheme: "http", description: "Media request and discovery manager", aliases: ["jellyseerr", "requests"] },
  { type: "tautulli", name: "Tautulli", category: "Media", icon: "tautulli", defaultPort: 8181, defaultScheme: "http", description: "Plex monitoring and analytics", aliases: ["plex", "statistics"] },
  { type: "tdarr", name: "Tdarr", category: "Media", icon: "tdarr", defaultPort: 8265, defaultScheme: "http", description: "Distributed media transcoding automation", aliases: ["transcode", "encoding"] },
  { type: "navidrome", name: "Navidrome", category: "Media", icon: "navidrome", defaultPort: 4533, defaultScheme: "http", description: "Self-hosted music streaming server", aliases: ["music", "subsonic"] },
  { type: "audiobookshelf", name: "Audiobookshelf", category: "Media", icon: "audiobookshelf", defaultPort: 13378, defaultScheme: "http", description: "Audiobook and podcast server", aliases: ["audiobooks", "podcasts"] },
  { type: "calibre-web", name: "Calibre-Web", category: "Media", icon: "calibre-web", defaultPort: 8083, defaultScheme: "http", description: "Web interface for ebook libraries", aliases: ["ebooks", "books", "calibre"] },

  // Download clients
  { type: "qbittorrent", name: "qBittorrent", category: "Downloads", icon: "qbittorrent", defaultPort: 8080, defaultScheme: "http", description: "BitTorrent client with web UI", aliases: ["torrent", "downloads"] },
  { type: "transmission", name: "Transmission", category: "Downloads", icon: "transmission", defaultPort: 9091, defaultScheme: "http", description: "Lightweight BitTorrent client", aliases: ["torrent", "downloads"] },
  { type: "deluge", name: "Deluge", category: "Downloads", icon: "deluge", defaultPort: 8112, defaultScheme: "http", description: "BitTorrent client with web UI", aliases: ["torrent", "downloads"] },
  { type: "sabnzbd", name: "SABnzbd", category: "Downloads", icon: "sabnzbd", defaultPort: 8080, defaultScheme: "http", description: "Usenet binary downloader", aliases: ["usenet", "nzb"] },
  { type: "nzbget", name: "NZBGet", category: "Downloads", icon: "nzbget", defaultPort: 6789, defaultScheme: "http", description: "Usenet downloader", aliases: ["usenet", "nzb"] },

  // Photos, files & documents
  { type: "immich", name: "Immich", category: "Photos & Files", icon: "immich", defaultPort: 2283, defaultScheme: "http", description: "Photo and video backup platform", aliases: ["photos", "google photos"] },
  { type: "nextcloud", name: "Nextcloud", category: "Photos & Files", icon: "nextcloud", defaultScheme: "https", description: "File sync, collaboration, and cloud suite", aliases: ["files", "cloud", "office"] },
  { type: "syncthing", name: "Syncthing", category: "Photos & Files", icon: "syncthing", defaultPort: 8384, defaultScheme: "http", description: "Peer-to-peer file synchronization", aliases: ["sync", "files"] },
  { type: "paperless-ngx", name: "Paperless-ngx", category: "Photos & Files", icon: "paperless-ngx", defaultPort: 8000, defaultScheme: "http", description: "Document management and OCR", aliases: ["documents", "paperless", "ocr"] },
  { type: "filebrowser", name: "File Browser", category: "Photos & Files", icon: null, defaultPort: 80, defaultScheme: "http", description: "Simple web file manager", aliases: ["files", "browser"] },
  { type: "homebox", name: "Homebox", category: "Photos & Files", icon: "homebox", defaultPort: 7745, defaultScheme: "http", description: "Home inventory and organization", aliases: ["inventory", "assets"] },

  // Home automation
  { type: "home-assistant", name: "Home Assistant", category: "Home & Automation", icon: "home-assistant", defaultPort: 8123, defaultScheme: "http", description: "Home automation platform", aliases: ["smart home", "hass", "ha"] },
  { type: "node-red", name: "Node-RED", category: "Home & Automation", icon: "node-red", defaultPort: 1880, defaultScheme: "http", description: "Flow-based automation and integration", aliases: ["automation", "flows"] },
  { type: "frigate", name: "Frigate", category: "Home & Automation", icon: "frigate", defaultPort: 8971, defaultScheme: "https", description: "NVR with local object detection", aliases: ["camera", "nvr", "security"] },

  // Monitoring & observability
  { type: "uptime-kuma", name: "Uptime Kuma", category: "Monitoring", icon: "uptime-kuma", defaultPort: 3001, defaultScheme: "http", description: "Uptime and endpoint monitoring", aliases: ["status", "monitoring"] },
  { type: "grafana", name: "Grafana", category: "Monitoring", icon: "grafana", defaultPort: 3000, defaultScheme: "http", description: "Dashboards and observability", aliases: ["metrics", "charts"] },
  { type: "prometheus", name: "Prometheus", category: "Monitoring", icon: "prometheus", defaultPort: 9090, defaultScheme: "http", description: "Metrics collection and alerting", aliases: ["metrics", "monitoring"] },
  { type: "netdata", name: "Netdata", category: "Monitoring", icon: "netdata", defaultPort: 19999, defaultScheme: "http", description: "Real-time infrastructure monitoring", aliases: ["metrics", "system"] },
  { type: "glances", name: "Glances", category: "Monitoring", icon: "glances", defaultPort: 61208, defaultScheme: "http", description: "Cross-platform system monitoring", aliases: ["metrics", "system"] },

  // Networking, proxy & identity
  { type: "pihole", name: "Pi-hole", category: "Networking & Security", icon: "pi-hole", defaultPort: 80, defaultScheme: "http", description: "Network-wide DNS filtering", aliases: ["dns", "adblock", "ad blocker"] },
  { type: "adguard-home", name: "AdGuard Home", category: "Networking & Security", icon: "adguard-home", defaultPort: 3000, defaultScheme: "http", description: "DNS filtering and network protection", aliases: ["dns", "adblock", "ad blocker"] },
  { type: "nginx-proxy-manager", name: "Nginx Proxy Manager", category: "Networking & Security", icon: "nginx-proxy-manager", defaultPort: 81, defaultScheme: "http", description: "Reverse proxy management UI", aliases: ["npm", "proxy", "nginx"] },
  { type: "traefik", name: "Traefik", category: "Networking & Security", icon: "traefik", defaultPort: 8080, defaultScheme: "http", description: "Cloud-native reverse proxy and ingress", aliases: ["proxy", "ingress"] },
  { type: "authentik", name: "Authentik", category: "Networking & Security", icon: "authentik", defaultPort: 9000, defaultScheme: "http", description: "Identity provider and single sign-on", aliases: ["sso", "oidc", "identity"] },
  { type: "authelia", name: "Authelia", category: "Networking & Security", icon: "authelia", defaultPort: 9091, defaultScheme: "http", description: "Authentication and authorization server", aliases: ["sso", "oidc", "identity"] },
  { type: "pocket-id", name: "Pocket ID", category: "Networking & Security", icon: "pocket-id", description: "Passkey-first OIDC identity provider", aliases: ["sso", "oidc", "identity", "passkey"] },

  // Infrastructure & container management
  { type: "dockge", name: "Dockge", category: "Infrastructure", icon: "dockge", defaultPort: 5001, defaultScheme: "http", description: "Compose stack manager", aliases: ["docker", "compose"], integration: "docker" },
  { type: "portainer", name: "Portainer", category: "Infrastructure", icon: "portainer", defaultPort: 9443, defaultScheme: "https", description: "Container and Docker management", aliases: ["docker", "containers"] },
  { type: "truenas", name: "TrueNAS", category: "Infrastructure", icon: "truenas", defaultScheme: "https", description: "NAS and storage platform", aliases: ["nas", "storage"] },
  { type: "unraid", name: "Unraid", category: "Infrastructure", icon: "unraid", defaultScheme: "http", description: "NAS, virtualization, and application host", aliases: ["nas", "storage", "docker"] },
  { type: "proxmox", name: "Proxmox VE", category: "Infrastructure", icon: "proxmox", defaultPort: 8006, defaultScheme: "https", description: "Virtualization management platform", aliases: ["vm", "virtualization", "pve"] },
  { type: "openmediavault", name: "OpenMediaVault", category: "Infrastructure", icon: "openmediavault", defaultPort: 80, defaultScheme: "http", description: "Debian-based NAS platform", aliases: ["omv", "nas", "storage"] },

  // Development
  { type: "gitea", name: "Gitea", category: "Development", icon: "gitea", defaultPort: 3000, defaultScheme: "http", description: "Self-hosted Git service", aliases: ["git", "source code"] },
  { type: "forgejo", name: "Forgejo", category: "Development", icon: "forgejo", defaultPort: 3000, defaultScheme: "http", description: "Community-driven Git forge", aliases: ["git", "source code"] },
  { type: "gitlab", name: "GitLab", category: "Development", icon: "gitlab", defaultScheme: "https", description: "DevOps and Git collaboration platform", aliases: ["git", "ci", "source code"] },
  { type: "jenkins", name: "Jenkins", category: "Development", icon: "jenkins", defaultPort: 8080, defaultScheme: "http", description: "Automation and CI/CD server", aliases: ["ci", "cd", "build"] },
  { type: "code-server", name: "code-server", category: "Development", icon: "code-server", defaultPort: 8080, defaultScheme: "http", description: "VS Code in the browser", aliases: ["vscode", "ide", "development"] },

  // Productivity & personal apps
  { type: "vaultwarden", name: "Vaultwarden", category: "Productivity", icon: "vaultwarden", defaultPort: 80, defaultScheme: "http", description: "Lightweight Bitwarden-compatible server", aliases: ["passwords", "bitwarden"] },
  { type: "mealie", name: "Mealie", category: "Productivity", icon: "mealie", defaultPort: 9000, defaultScheme: "http", description: "Recipe manager and meal planner", aliases: ["recipes", "food"] },
  { type: "freshrss", name: "FreshRSS", category: "Productivity", icon: "freshrss", defaultPort: 80, defaultScheme: "http", description: "RSS and Atom feed reader", aliases: ["rss", "feeds", "news"] },

  // Gaming
  { type: "pterodactyl", name: "Pterodactyl", category: "Gaming", icon: "pterodactyl", defaultScheme: "https", description: "Game server management panel", aliases: ["game server", "minecraft", "panel"] },

  // Always-available fallbacks
  { type: "link", name: "Generic Web Service", category: "Custom", icon: null, defaultScheme: "https", description: "Add any web application or device UI", aliases: ["custom", "url", "link"] },
  { type: "other", name: "Custom Service", category: "Custom", icon: null, defaultScheme: "https", description: "Create a fully custom dashboard card", aliases: ["custom", "unknown", "other"] },
];

export const CATALOG_BY_TYPE = Object.fromEntries(SERVICE_CATALOG.map((entry) => [entry.type, entry])) as Record<string, CatalogEntry>;
export const CATALOG_CATEGORIES = ["All", ...Array.from(new Set(SERVICE_CATALOG.map((entry) => entry.category)))];

export function catalogSearchText(entry: CatalogEntry): string {
  return [entry.name, entry.type, entry.category, entry.description, ...(entry.aliases ?? [])].join(" ").toLowerCase();
}

export function urlPlaceholder(entry: CatalogEntry): string {
  const scheme = entry.defaultScheme ?? "http";
  const port = entry.defaultPort ? `:${entry.defaultPort}` : "";
  return `${scheme}://server.local${port}`;
}
