"""Product Intelligence Engine — backward-compatible re-export shim.

The actual implementation lives in mandarin/intelligence/ package.
This file exists for backward compatibility with existing imports.
"""

from .intelligence import run_product_audit  # noqa: F401
