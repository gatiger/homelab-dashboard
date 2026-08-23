#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "registry" / "index.json"
ALLOWED_CAPABILITIES = {"page_templates", "service_catalog"}
ALLOWED_PERMISSIONS = {"dashboard:register-templates", "catalog:register-entries"}
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def fail(message: str) -> None:
    raise SystemExit(f"registry validation failed: {message}")


def main() -> None:
    try:
        index = json.loads(INDEX.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))
    if index.get("format") != "homelab-dashboard-extension-registry" or index.get("schema_version") != 1:
        fail("unsupported registry format/schema")
    seen: set[str] = set()
    for entry in index.get("entries", []):
        extension_id = entry.get("id")
        if not isinstance(extension_id, str) or extension_id in seen:
            fail(f"duplicate/invalid id: {extension_id!r}")
        seen.add(extension_id)
        if not VERSION.fullmatch(str(entry.get("version", ""))):
            fail(f"invalid version for {extension_id}")
        package_rel = entry.get("package")
        if not isinstance(package_rel, str) or package_rel.startswith(("/", "http://", "https://")) or ".." in Path(package_rel).parts:
            fail(f"unsafe package path for {extension_id}")
        package_path = (INDEX.parent / package_rel).resolve()
        if INDEX.parent.resolve() not in package_path.parents:
            fail(f"package escapes registry directory for {extension_id}")
        if not package_path.is_file():
            fail(f"package missing for {extension_id}: {package_rel}")
        raw = package_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != str(entry.get("sha256", "")).lower():
            fail(f"checksum mismatch for {extension_id}")
        try:
            package = json.loads(raw)
        except json.JSONDecodeError as exc:
            fail(f"invalid package JSON for {extension_id}: {exc}")
        for field in ("id", "name", "version", "author", "description", "type", "min_dashboard_version", "capabilities", "permissions"):
            if package.get(field) != entry.get(field):
                fail(f"registry/package {field} mismatch for {extension_id}")
        if not set(entry.get("capabilities", [])).issubset(ALLOWED_CAPABILITIES):
            fail(f"unsupported capabilities for {extension_id}")
        if not set(entry.get("permissions", [])).issubset(ALLOWED_PERMISSIONS):
            fail(f"unsupported permissions for {extension_id}")
    print(f"registry valid: {len(seen)} package(s)")


if __name__ == "__main__":
    main()
