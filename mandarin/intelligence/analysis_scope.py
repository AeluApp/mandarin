"""AnalysisScope — solo vs cohort mode for intelligence queries (Doc 7).

Provides a dataclass that encapsulates user filtering for both
single-user and classroom-level analysis. New analyzers can optionally
accept a scope parameter; existing analyzers are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnalysisScope:
    """Defines the scope of an intelligence analysis query."""

    user_id: Optional[int] = None
    classroom_id: Optional[int] = None
    user_ids: list[int] = field(default_factory=list)

    @property
    def is_solo(self) -> bool:
        return self.user_id is not None and not self.user_ids

    @property
    def is_cohort(self) -> bool:
        return bool(self.user_ids)

    def user_filter_sql(self, alias: str = "") -> tuple[str, list]:
        """Return (WHERE fragment, params) for parameterized user filtering.

        The fragment includes the column reference but NOT the WHERE keyword,
        so callers can combine with other conditions.
        """
        col = f"{alias}.user_id" if alias else "user_id"
        if self.is_solo:
            return f"{col} = ?", [self.user_id]
        if self.is_cohort:
            placeholders = ",".join("?" for _ in self.user_ids)
            return f"{col} IN ({placeholders})", list(self.user_ids)
        return "1=1", []

    @classmethod
    def solo(cls, user_id: int) -> AnalysisScope:
        return cls(user_id=user_id)

    @classmethod
    def cohort(cls, classroom_id: int, user_ids: list[int]) -> AnalysisScope:
        return cls(classroom_id=classroom_id, user_ids=user_ids)
