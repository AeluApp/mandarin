"""Central data-directory resolver for the mandarin package.

Resolves the static data directory (JSON files, HSK vocab, grammar patterns, etc.)
in both development and Docker/pip-installed deployments.

Problem: when the package is installed via `pip install .`, Python files land in
`site-packages/mandarin/`, but the `data/` directory is at `/app/data/` in the
Docker image.  Using `Path(__file__).parent.parent / "data"` resolves correctly
in development but produces `site-packages/data/` (which does not exist) after
installation.

Resolution order:
  1. MANDARIN_STATIC_DATA env var — explicit override for unusual deployments
  2. `Path(__file__).parent.parent / "data"` — correct for `pip install -e .`
     (editable / development) or direct `python -m mandarin` from project root
  3. `/app/data` — correct for the Docker image after `pip install .`
"""

import os
from pathlib import Path


def _resolve() -> Path:
    if override := os.environ.get("MANDARIN_STATIC_DATA", "").strip():
        return Path(override)

    # Development / editable install: data/ is two levels up from this file.
    dev_candidate = Path(__file__).parent.parent / "data"
    if dev_candidate.is_dir():
        return dev_candidate

    # Docker production: data/ was COPY'd to /app/data in the Dockerfile.
    docker_candidate = Path("/app/data")
    if docker_candidate.is_dir():
        return docker_candidate

    # Fallback (returns non-existent path; callers raise FileNotFoundError).
    return dev_candidate


#: Resolved path to the static data directory.  Import and use this constant
#: instead of computing ``Path(__file__).parent.parent / "data"`` inline.
DATA_DIR: Path = _resolve()
