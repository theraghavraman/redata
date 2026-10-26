#!/usr/bin/env python3
"""Reconcile the Python license inventory with the CycloneDX environment SBOM.

The audit tools themselves can appear in the SBOM but be omitted by
pip-licenses. This script adds those components to the inventory using the
license metadata already present in the SBOM, and fills the known pymssql
metadata gap only when pip-licenses supplies the full LGPL v2.1 license text.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SBOM_PATH = Path("sbom.cdx.json")
LICENSES_PATH = Path("licenses-resolved.json")


def key(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def sbom_license(component: dict) -> str | None:
    values: list[str] = []
    for item in component.get("licenses", []):
        # CycloneDX permits either a nested {"license": {...}} object or
        # a direct license/expression object in this array.
        license_obj = item.get("license", item)
        if license_obj.get("expression"):
            values.append(license_obj["expression"])
        elif license_obj.get("id"):
            values.append(license_obj["id"])
        elif license_obj.get("name"):
            values.append(license_obj["name"])
    return " OR ".join(dict.fromkeys(values)) if values else None


def main() -> int:
    sbom = json.loads(SBOM_PATH.read_text(encoding="utf-8"))
    inventory = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    if not isinstance(inventory, list):
        raise ValueError("licenses-resolved.json must contain a JSON array")

    inventory_by_name = {key(item["Name"]): item for item in inventory}
    components = sbom.get("components", [])
    missing: list[str] = []

    for component in components:
        name = component.get("name")
        version = component.get("version", "")
        if not name:
            continue
        normalized = key(name)
        license_value = sbom_license(component)

        if not license_value and normalized == "pymssql":
            resolved = inventory_by_name.get(normalized, {}).get("License", "")
            first_lines = resolved.splitlines()[:3]
            license_text = "\n".join(first_lines).casefold()
            if "gnu lesser general public license" in license_text and "version 2.1" in license_text:
                license_value = "LGPL-2.1-or-later"
                component["licenses"] = [{
                    "license": {"acknowledgement": "declared", "id": license_value}
                }]
                component.setdefault("properties", []).append({
                    "name": "redata:license:normalization",
                    "value": "Normalized from pip-licenses full LGPL v2.1-or-later text and pymssql upstream source license; verify wheel/bundled FreeTDS notices before redistribution."
                })

        # The protobuf Python package is distributed under BSD-3-Clause. Some
        # CycloneDX environment scans omit that upstream license metadata even
        # when the installed package itself is correctly identified.
        if not license_value and normalized == "protobuf":
            license_value = "BSD-3-Clause"
            component["licenses"] = [{
                "license": {"acknowledgement": "declared", "id": license_value}
            }]
            component.setdefault("properties", []).append({
                "name": "redata:license:normalization",
                "value": "Filled from the protobuf Python package's upstream BSD-3-Clause license; verify the exact distribution's license files before redistribution."
            })

        if not license_value:
            missing.append(f"{name}=={version}")
            continue

        if normalized not in inventory_by_name:
            inventory_by_name[normalized] = {
                "Name": name,
                "Version": version,
                "License": license_value,
                "License Source": "CycloneDX component metadata; added to reconcile audit-tool dependencies"
            }
        else:
            row = inventory_by_name[normalized]
            if not row.get("Version"):
                row["Version"] = version

    if missing:
        print("ERROR: components still lack license metadata: " + ", ".join(sorted(missing)), file=sys.stderr)
        return 1

    reconciled = sorted(inventory_by_name.values(), key=lambda item: key(item["Name"]))
    LICENSES_PATH.write_text(json.dumps(reconciled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SBOM_PATH.write_text(json.dumps(sbom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    sbom_names = {key(item["name"]) for item in components if item.get("name")}
    inventory_names = {key(item["Name"]) for item in reconciled}
    if sbom_names != inventory_names:
        print(
            "ERROR: inventory/SBOM mismatch after reconciliation: "
            f"SBOM-only={sorted(sbom_names - inventory_names)}, "
            f"inventory-only={sorted(inventory_names - sbom_names)}",
            file=sys.stderr,
        )
        return 1

    print(f"Reconciled {len(components)} SBOM components with {len(reconciled)} license inventory entries.")
    print("All SBOM components have license metadata; inventory and SBOM package sets match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
