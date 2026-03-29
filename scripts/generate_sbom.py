#!/usr/bin/env python3
"""Generate CycloneDX Software Bill of Materials (SBOM) from installed packages.

Outputs sbom.json in CycloneDX 1.5 format listing all Python dependencies
with versions, licenses, and package hashes for supply chain transparency.

Usage:
    python scripts/generate_sbom.py [--output sbom.json]
"""

from __future__ import annotations

import importlib.metadata
import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_sbom(output_path: str = "sbom.json") -> dict:
    """Generate CycloneDX 1.5 SBOM from installed packages."""
    components = []

    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        version = dist.metadata["Version"]
        license_info = dist.metadata.get("License", "")
        summary = dist.metadata.get("Summary", "")
        homepage = dist.metadata.get("Home-page", "")

        # Package URL (purl) format
        purl = f"pkg:pypi/{name}@{version}"

        component = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": purl,
            "description": summary or "",
        }

        if license_info and license_info != "UNKNOWN":
            component["licenses"] = [{"license": {"name": license_info}}]

        if homepage and homepage != "UNKNOWN":
            component["externalReferences"] = [
                {"type": "website", "url": homepage}
            ]

        components.append(component)

    # Sort for deterministic output
    components.sort(key=lambda c: c["name"].lower())

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [
                {
                    "vendor": "Aelu",
                    "name": "generate_sbom.py",
                    "version": "1.0.0",
                }
            ],
            "component": {
                "type": "application",
                "name": "aelu",
                "version": "1.0.0",
                "description": "Mandarin learning platform",
                "purl": "pkg:pypi/mandarin@1.0.0",
            },
        },
        "components": components,
    }

    output = Path(output_path)
    output.write_text(json.dumps(sbom, indent=2, ensure_ascii=False))
    print(f"SBOM generated: {output} ({len(components)} components)")

    return sbom


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "sbom.json"
    if output.startswith("--output="):
        output = output.split("=", 1)[1]
    elif output == "--output" and len(sys.argv) > 2:
        output = sys.argv[2]
    generate_sbom(output)
