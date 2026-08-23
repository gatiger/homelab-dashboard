# Contributing

Thanks for helping improve the project.

## Early contribution areas

- New service integrations
- Dashboard widgets
- Authentication providers
- Accessibility improvements
- Documentation and translations
- Testing on different self-hosted platforms

## Development workflow

1. Create a fork.
2. Create a focused feature branch.
3. Add or update tests when practical.
4. Run the frontend and backend locally.
5. Submit a pull request explaining the problem and solution.

Until the plugin contract is finalized, open an issue before building a large integration.

## Theme contributions

Theme packages should use the documented v1 JSON format in `docs/extensions/themes.md`. Community themes must not depend on external scripts, CSS, fonts, or network resources. Keep theme IDs stable and use semantic versioning for updates.

The repository includes `examples/themes/midnight-blue.json` as a starting point.

## Data-only extension contributions

v0.16+ supports versioned JSON page-template and service-catalog packs without modifying core source code. Before proposing a built-in catalog/template change, consider whether it is better as a community data pack. See `docs/extensions/packages.md` and `examples/extensions/`.

Do not submit extension packages that attempt to embed executable scripts, shell commands, secret material, or privileged Docker/filesystem/network behavior. The current schema intentionally rejects unknown fields and permissions outside the documented safe allow-list.


## Extension registry contributions

Registry additions belong under `registry/packages/` with matching metadata in `registry/index.json`. Keep package paths relative to the registry, increment versions when package bytes change, and update the SHA-256 checksum. Run `python scripts/validate-registry.py` before opening a pull request; CI runs the same validation. Trust labels are assigned by registry maintainers and do not bypass package validation.
