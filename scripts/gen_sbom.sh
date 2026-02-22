#!/bin/bash
# Generate Software Bill of Materials (SBOM) in CycloneDX format.
set -euo pipefail

OUTPUT="${1:-docs/sbom.json}"

echo "Generating SBOM..."

if command -v cyclonedx-py &>/dev/null; then
  cyclonedx-py requirements -i requirements.txt -o "${OUTPUT}" --format json
  echo "SBOM written to ${OUTPUT}"
elif command -v pip &>/dev/null; then
  echo "cyclonedx-py not installed. Installing..."
  pip install cyclonedx-bom
  cyclonedx-py requirements -i requirements.txt -o "${OUTPUT}" --format json
  echo "SBOM written to ${OUTPUT}"
else
  echo "ERROR: pip not available"
  exit 1
fi
