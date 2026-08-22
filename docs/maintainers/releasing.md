# Maintainer release process

1. Update application versions and `CHANGELOG.md`.
2. Push to `main` and confirm CI passes.
3. Create and push a `vX.Y.Z` tag / GitHub Release.
4. The `Publish container image` workflow publishes multi-architecture images to GitHub Container Registry:
   - `ghcr.io/gatiger/homelab-dashboard:X.Y.Z`
   - `ghcr.io/gatiger/homelab-dashboard:X.Y`
   - `ghcr.io/gatiger/homelab-dashboard:latest`
5. Main-branch builds publish `:edge`.

## First GHCR publication

GitHub Container Registry packages may initially be private. After the first successful package publication, open the package settings on GitHub and set the package visibility to **Public** so anonymous Docker hosts can pull the image.

GitHub reference:
- https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images
- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
