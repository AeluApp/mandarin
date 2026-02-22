#!/usr/bin/env python3
"""Generate data dictionary markdown from the live database schema.

Outputs docs/data-dictionary.md with table definitions, column types,
PII classification, and retention policies.
"""

import sqlite3
import sys
from pathlib import Path

# PII classification: columns that contain personally identifiable information
PII_COLUMNS = {
    "email", "display_name", "password_hash", "ip_address", "user_agent",
    "stripe_customer_id", "stripe_subscription_id", "reset_token_hash",
    "refresh_token_hash", "totp_secret", "totp_backup_codes",
    "email_verify_token", "partner_email",
}

# Sensitive but not PII
SENSITIVE_COLUMNS = {
    "token", "code", "secret", "hash",
}

# Tables to skip
SKIP_TABLES = {"sqlite_sequence", "schema_version"}


def classify_column(col_name: str) -> str:
    """Classify a column as PII, sensitive, or public."""
    if col_name in PII_COLUMNS:
        return "PII"
    for s in SENSITIVE_COLUMNS:
        if s in col_name:
            return "Sensitive"
    return ""


def main():
    db_path = Path(__file__).parent.parent / "data" / "mandarin.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall() if r[0] not in SKIP_TABLES]

    # Load retention policies
    retention = {}
    try:
        for r in conn.execute("SELECT table_name, retention_days, description FROM retention_policy").fetchall():
            retention[r["table_name"]] = {
                "days": r["retention_days"],
                "description": r["description"] or "",
            }
    except sqlite3.OperationalError:
        pass

    lines = [
        "# Data Dictionary",
        "",
        f"Generated from database schema. {len(tables)} tables.",
        "",
        "## PII Classification Legend",
        "",
        "| Tag | Meaning |",
        "|-----|---------|",
        "| PII | Personally Identifiable Information — subject to GDPR |",
        "| Sensitive | Security-sensitive — encrypted or hashed at rest |",
        "",
    ]

    for table in tables:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        ret_info = retention.get(table, {})
        ret_str = ""
        if ret_info:
            days = ret_info["days"]
            ret_str = f" | Retention: {'indefinite' if days < 0 else f'{days} days'}"
            if ret_info["description"]:
                ret_str += f" ({ret_info['description']})"

        has_user_id = any(c["name"] == "user_id" for c in cols)

        lines.append(f"## `{table}`")
        lines.append("")
        lines.append(f"Rows: {row_count} | User-scoped: {'Yes' if has_user_id else 'No'}{ret_str}")
        lines.append("")
        lines.append("| Column | Type | Nullable | Classification |")
        lines.append("|--------|------|----------|----------------|")

        for col in cols:
            nullable = "Yes" if not col["notnull"] else "No"
            classification = classify_column(col["name"])
            lines.append(f"| `{col['name']}` | {col['type'] or 'TEXT'} | {nullable} | {classification} |")

        lines.append("")

    output_path = Path(__file__).parent.parent / "docs" / "data-dictionary.md"
    output_path.write_text("\n".join(lines) + "\n")
    print(f"Data dictionary written to {output_path}")


if __name__ == "__main__":
    main()
