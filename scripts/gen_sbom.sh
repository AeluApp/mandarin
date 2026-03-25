#!/bin/bash
# Generate Software Bill of Materials (SBOM) in CycloneDX format.
set -euo pipefail

OUTPUT="${1:-docs/sbom.json}"

echo "Generating SBOM..."

# Install requirements first so they're in the environment
pip install -r requirements.txt -q 2>/dev/null || true

if command -v cyclonedx-py &>/dev/null; then
  cyclonedx-py environment -o "${OUTPUT}" --output-format json 2>/dev/null || \
  cyclonedx-py requirements -i requirements.txt -o "${OUTPUT}" --format json 2>/dev/null || \
  { echo "cyclonedx-py failed, generating minimal SBOM"; python -c "
import json, pkg_resources
pkgs = [{'name': d.project_name, 'version': d.version} for d in pkg_resources.working_set]
json.dump({'bomFormat': 'CycloneDX', 'specVersion': '1.4', 'components': pkgs}, open('${OUTPUT}', 'w'), indent=2)
"; }
  echo "SBOM written to ${OUTPUT}"
else
  echo "cyclonedx-py not found. Generating minimal SBOM..."
  python -c "
import json, pkg_resources
pkgs = [{'name': d.project_name, 'version': d.version} for d in pkg_resources.working_set]
json.dump({'bomFormat': 'CycloneDX', 'specVersion': '1.4', 'components': pkgs}, open('${OUTPUT}', 'w'), indent=2)
"
  echo "SBOM written to ${OUTPUT}"
fi
