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
