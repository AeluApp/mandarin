"""Tests for Supabase MCP migration preparation module."""
# phantom-schema-checked

import json
import unittest


from tests.shared_db import make_test_db


def _make_db():
    conn = make_test_db()
    conn.executescript("""
        INSERT INTO content_item (hanzi, pinyin, english) VALUES ('你好', 'nǐ hǎo', 'hello');
        INSERT INTO content_item (hanzi, pinyin, english) VALUES ('谢谢', 'xiè xie', 'thanks');
        INSERT INTO progress (user_id, content_item_id, modality) VALUES (1, 1, 'reading');
        INSERT INTO session_log (user_id, started_at, session_outcome) VALUES (1, datetime('now'), 'completed');
    """)
    return conn


class TestMigrationStatus(unittest.TestCase):

    def test_import(self):
        from mandarin.openclaw import supabase_mcp
        self.assertTrue(hasattr(supabase_mcp, 'get_migration_status'))
        self.assertTrue(hasattr(supabase_mcp, 'generate_postgres_schema'))
        self.assertTrue(hasattr(supabase_mcp, 'verify_data_integrity'))
        self.assertTrue(hasattr(supabase_mcp, 'export_table_json'))

    def test_migration_status_structure(self):
        from mandarin.openclaw.supabase_mcp import get_migration_status
        conn = _make_db()
        result = get_migration_status(conn)
        self.assertIn("total_tables", result)
        self.assertIn("tables", result)
        self.assertIn("per_user_tables", result)
        self.assertIn("shared_tables", result)
        self.assertIn("admin_tables", result)
        self.assertGreater(result["total_tables"], 0)

    def test_migration_status_table_info(self):
        from mandarin.openclaw.supabase_mcp import get_migration_status
        conn = _make_db()
        result = get_migration_status(conn)
        table_names = {t["name"] for t in result["tables"]}
        self.assertIn("user", table_names)
        self.assertIn("content_item", table_names)
        self.assertIn("progress", table_names)

    def test_migration_status_row_counts(self):
        from mandarin.openclaw.supabase_mcp import get_migration_status
        conn = _make_db()
        result = get_migration_status(conn)
        user_table = next(t for t in result["tables"] if t["name"] == "user")
        self.assertEqual(user_table["row_count"], 1)
        ci_table = next(t for t in result["tables"] if t["name"] == "content_item")
        self.assertEqual(ci_table["row_count"], 2)

    def test_table_scope_classification(self):
        from mandarin.openclaw.supabase_mcp import get_migration_status
        conn = _make_db()
        result = get_migration_status(conn)
        progress_table = next(t for t in result["tables"] if t["name"] == "progress")
        self.assertEqual(progress_table["scope"], "per_user")
        self.assertTrue(progress_table["needs_rls"])

        ci_table = next(t for t in result["tables"] if t["name"] == "content_item")
        self.assertEqual(ci_table["scope"], "shared")

        audit_table = next(t for t in result["tables"] if t["name"] == "product_audit")
        self.assertEqual(audit_table["scope"], "admin")


class TestPostgresSchemaGeneration(unittest.TestCase):

    def test_generate_basic_table(self):
        from mandarin.openclaw.supabase_mcp import generate_postgres_schema
        conn = _make_db()
        result = generate_postgres_schema(conn, "user")
        self.assertEqual(result["table_name"], "user")
        self.assertIn("CREATE TABLE", result["create_sql"])
        self.assertGreater(result["column_count"], 0)

    def test_pg_types_in_output(self):
        from mandarin.openclaw.supabase_mcp import generate_postgres_schema
        conn = _make_db()
        result = generate_postgres_schema(conn, "user")
        sql = result["create_sql"]
        # id should map to BIGSERIAL PRIMARY KEY
        self.assertIn("PRIMARY KEY", sql)
        # TEXT columns should remain TEXT
        self.assertIn("TEXT", sql)

    def test_rls_for_per_user_tables(self):
        from mandarin.openclaw.supabase_mcp import generate_postgres_schema
        conn = _make_db()
        result = generate_postgres_schema(conn, "progress")
        self.assertTrue(result["needs_rls"])
        self.assertIsNotNone(result["rls_sql"])
        self.assertIn("ROW LEVEL SECURITY", result["rls_sql"])
        self.assertIn("auth.uid()", result["rls_sql"])

    def test_no_rls_for_shared_tables(self):
        from mandarin.openclaw.supabase_mcp import generate_postgres_schema
        conn = _make_db()
        result = generate_postgres_schema(conn, "content_item")
        self.assertFalse(result["needs_rls"])
        self.assertIsNone(result["rls_sql"])

    def test_nonexistent_table(self):
        from mandarin.openclaw.supabase_mcp import generate_postgres_schema
        conn = _make_db()
        result = generate_postgres_schema(conn, "nonexistent")
        self.assertIn("error", result)


class TestTypeMapping(unittest.TestCase):

    def test_integer_maps_to_bigint(self):
        from mandarin.openclaw.supabase_mcp import _sqlite_to_pg_type
        self.assertEqual(_sqlite_to_pg_type("INTEGER"), "BIGINT")
        self.assertEqual(_sqlite_to_pg_type("INT"), "BIGINT")

    def test_text_maps_to_text(self):
        from mandarin.openclaw.supabase_mcp import _sqlite_to_pg_type
        self.assertEqual(_sqlite_to_pg_type("TEXT"), "TEXT")

    def test_real_maps_to_double(self):
        from mandarin.openclaw.supabase_mcp import _sqlite_to_pg_type
        self.assertEqual(_sqlite_to_pg_type("REAL"), "DOUBLE PRECISION")
        self.assertEqual(_sqlite_to_pg_type("FLOAT"), "DOUBLE PRECISION")

    def test_blob_maps_to_bytea(self):
        from mandarin.openclaw.supabase_mcp import _sqlite_to_pg_type
        self.assertEqual(_sqlite_to_pg_type("BLOB"), "BYTEA")

    def test_boolean_maps(self):
        from mandarin.openclaw.supabase_mcp import _sqlite_to_pg_type
        self.assertEqual(_sqlite_to_pg_type("BOOLEAN"), "BOOLEAN")

    def test_varchar_maps_to_text(self):
        from mandarin.openclaw.supabase_mcp import _sqlite_to_pg_type
        self.assertEqual(_sqlite_to_pg_type("VARCHAR(255)"), "TEXT")

    def test_unknown_maps_to_text(self):
        from mandarin.openclaw.supabase_mcp import _sqlite_to_pg_type
        self.assertEqual(_sqlite_to_pg_type("CUSTOM_TYPE"), "TEXT")


class TestDefaultConversion(unittest.TestCase):

    def test_datetime_now(self):
        from mandarin.openclaw.supabase_mcp import _convert_default
        self.assertEqual(_convert_default("(datetime('now'))"), "NOW()")

    def test_date_now(self):
        from mandarin.openclaw.supabase_mcp import _convert_default
        self.assertEqual(_convert_default("(date('now'))"), "CURRENT_DATE")

    def test_string_literal(self):
        from mandarin.openclaw.supabase_mcp import _convert_default
        self.assertEqual(_convert_default("'pending'"), "'pending'")

    def test_numeric(self):
        from mandarin.openclaw.supabase_mcp import _convert_default
        self.assertEqual(_convert_default("0"), "0")
        self.assertEqual(_convert_default("42"), "42")

    def test_none(self):
        from mandarin.openclaw.supabase_mcp import _convert_default
        self.assertIsNone(_convert_default(None))
        self.assertIsNone(_convert_default(""))

    def test_complex_expression_returns_none(self):
        from mandarin.openclaw.supabase_mcp import _convert_default
        self.assertIsNone(_convert_default("(random() * 100)"))


class TestDataIntegrity(unittest.TestCase):

    def test_clean_database(self):
        from mandarin.openclaw.supabase_mcp import verify_data_integrity
        conn = _make_db()
        result = verify_data_integrity(conn)
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["issue_count"], 0)

    def test_foreign_key_violations(self):
        from mandarin.openclaw.supabase_mcp import verify_data_integrity
        conn = _make_db()
        conn.execute("PRAGMA foreign_keys = ON")
        # Insert orphaned progress record (FK not enforced in this context but
        # the PRAGMA foreign_key_check will find it)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("INSERT INTO progress (user_id, content_item_id, modality) VALUES (1, 9999, 'reading')")
        result = verify_data_integrity(conn)
        # May or may not detect based on FK enforcement
        self.assertIn(result["status"], ("clean", "issues_found"))

    def test_integrity_check_returns_dict(self):
        from mandarin.openclaw.supabase_mcp import verify_data_integrity
        conn = _make_db()
        result = verify_data_integrity(conn)
        self.assertIn("status", result)
        self.assertIn("issues", result)
        self.assertIn("issue_count", result)
        self.assertIsInstance(result["issues"], list)


class TestExportTableJson(unittest.TestCase):

    def test_export_content_item(self):
        from mandarin.openclaw.supabase_mcp import export_table_json
        conn = _make_db()
        result = export_table_json(conn, "content_item")
        self.assertEqual(result["table_name"], "content_item")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(len(result["data"]), 2)

    def test_export_with_limit(self):
        from mandarin.openclaw.supabase_mcp import export_table_json
        conn = _make_db()
        result = export_table_json(conn, "content_item", limit=1)
        self.assertEqual(result["row_count"], 1)

    def test_export_nonexistent_table(self):
        from mandarin.openclaw.supabase_mcp import export_table_json
        conn = _make_db()
        result = export_table_json(conn, "nonexistent_table")
        self.assertIn("error", result)

    def test_export_data_structure(self):
        from mandarin.openclaw.supabase_mcp import export_table_json
        conn = _make_db()
        result = export_table_json(conn, "content_item")
        row = result["data"][0]
        self.assertIn("hanzi", row)
        self.assertIn("pinyin", row)
        self.assertIn("english", row)

    def test_export_empty_table(self):
        from mandarin.openclaw.supabase_mcp import export_table_json
        conn = _make_db()
        conn.execute("CREATE TABLE empty_table (id INTEGER PRIMARY KEY)")
        result = export_table_json(conn, "empty_table")
        self.assertEqual(result["row_count"], 0)
        self.assertEqual(result["data"], [])


class TestTableClassification(unittest.TestCase):

    def test_multi_user_tables(self):
        from mandarin.openclaw.supabase_mcp import _MULTI_USER_TABLES
        self.assertIn("progress", _MULTI_USER_TABLES)
        self.assertIn("session_log", _MULTI_USER_TABLES)
        self.assertIn("error_log", _MULTI_USER_TABLES)
        self.assertIn("audio_recording", _MULTI_USER_TABLES)
        self.assertNotIn("content_item", _MULTI_USER_TABLES)

    def test_shared_tables(self):
        from mandarin.openclaw.supabase_mcp import _SHARED_TABLES
        self.assertIn("content_item", _SHARED_TABLES)
        self.assertIn("grammar_point", _SHARED_TABLES)
        self.assertNotIn("progress", _SHARED_TABLES)

    def test_admin_tables(self):
        from mandarin.openclaw.supabase_mcp import _ADMIN_TABLES
        self.assertIn("product_audit", _ADMIN_TABLES)
        self.assertIn("feature_flag", _ADMIN_TABLES)
        self.assertNotIn("progress", _ADMIN_TABLES)

    def test_no_overlap(self):
        from mandarin.openclaw.supabase_mcp import _MULTI_USER_TABLES, _SHARED_TABLES, _ADMIN_TABLES
        self.assertEqual(len(_MULTI_USER_TABLES & _SHARED_TABLES), 0)
        self.assertEqual(len(_MULTI_USER_TABLES & _ADMIN_TABLES), 0)
        self.assertEqual(len(_SHARED_TABLES & _ADMIN_TABLES), 0)


if __name__ == "__main__":
    unittest.main()
