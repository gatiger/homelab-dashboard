# Maintainer release process

1. Update application versions and `CHANGELOG.md`.
2. Push to `main` and confirm CI passes.
3. Create and push a `vX.Y.Z` tag / GitHub Release.
4. The `Publish container image` workflow publishes both multi-architecture images to GitHub Container Registry:
   - `ghcr.io/gatiger/homelab-dashboard:X.Y.Z`
   - `ghcr.io/gatiger/homelab-dashboard:X.Y`
   - `ghcr.io/gatiger/homelab-dashboard:latest`
   - `ghcr.io/gatiger/homelab-dashboard-agent:X.Y.Z`
   - `ghcr.io/gatiger/homelab-dashboard-agent:X.Y`
   - `ghcr.io/gatiger/homelab-dashboard-agent:latest`
5. The publish workflow can also be run manually; manual dispatch publishes `:edge` for both images. Ordinary pushes to `main` run CI but do not publish GHCR images.

## First GHCR publication

GitHub Container Registry packages may initially be private. After the first successful publication of each package, open its package settings on GitHub and set visibility to **Public** so anonymous Docker hosts can pull the images.

This is particularly important for the v0.11 update-agent package because it is a separate GHCR package from the main dashboard image.

GitHub reference:
- https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images
- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
