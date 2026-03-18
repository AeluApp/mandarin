"""Tests for mem0 conversation memory module (mandarin/ai/memory.py).

Verifies add_memory(), search_memory(), _get_memory() singleton behavior,
and graceful degradation when mem0 is not installed.
"""

import sqlite3
import unittest
from unittest.mock import patch, MagicMock, PropertyMock


def _reset_memory_globals():
    """Reset module-level singleton state between tests."""
    import mandarin.ai.memory as mem_mod
    mem_mod._memory_instance = None
    mem_mod._mem0_available = None


class TestGetMemorySingleton(unittest.TestCase):
    """_get_memory() returns a singleton Memory instance or None."""

    def setUp(self):
        _reset_memory_globals()

    def tearDown(self):
        _reset_memory_globals()

    @patch("mandarin.ai.memory.Memory", create=True)
    def test_singleton_returns_same_instance(self, _mock_cls):
        """Calling _get_memory() twice returns the exact same object."""
        import mandarin.ai.memory as mem_mod

        sentinel = MagicMock(name="MemoryInstance")

        # Patch the import path so `from mem0 import Memory` succeeds
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = sentinel

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            first = mem_mod._get_memory()
            second = mem_mod._get_memory()

        self.assertIs(first, second)
        # from_config should only be called once (singleton)
        self.assertEqual(fake_mem0.Memory.from_config.call_count, 1)

    def test_mem0_not_installed_returns_none(self):
        """When mem0 is not importable, _get_memory() returns None."""
        import mandarin.ai.memory as mem_mod

        # Force ImportError on `from mem0 import Memory`
        with patch.dict("sys.modules", {"mem0": None}):
            result = mem_mod._get_memory()

        self.assertIsNone(result)

    def test_mem0_not_installed_caches_false(self):
        """After ImportError, subsequent calls skip import and return None."""
        import mandarin.ai.memory as mem_mod

        with patch.dict("sys.modules", {"mem0": None}):
            mem_mod._get_memory()
            self.assertIs(mem_mod._mem0_available, False)
            # Second call should short-circuit
            result = mem_mod._get_memory()

        self.assertIsNone(result)


class TestAddMemory(unittest.TestCase):
    """add_memory() stores a conversation turn via mem.add()."""

    def setUp(self):
        _reset_memory_globals()

    def tearDown(self):
        _reset_memory_globals()

    def test_add_memory_calls_mem_add(self):
        """add_memory() formats messages and calls mem.add() correctly."""
        import mandarin.ai.memory as mem_mod

        mock_mem = MagicMock()
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = mock_mem

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            mem_mod.add_memory(
                user_id="user_abc123",
                message="What does 你好 mean?",
                response="It means hello.",
                channel="telegram",
            )

        mock_mem.add.assert_called_once()
        call_args = mock_mem.add.call_args
        messages = call_args[0][0]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "What does 你好 mean?")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(call_args[1]["user_id"], "user_abc123")
        self.assertEqual(call_args[1]["metadata"]["channel"], "telegram")

    def test_add_memory_no_channel_omits_metadata(self):
        """When channel is empty, metadata dict should be empty."""
        import mandarin.ai.memory as mem_mod

        mock_mem = MagicMock()
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = mock_mem

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            mem_mod.add_memory(
                user_id="user_xyz",
                message="hi",
                response="hello",
                channel="",
            )

        call_args = mock_mem.add.call_args
        self.assertEqual(call_args[1]["metadata"], {})

    def test_add_memory_graceful_when_mem0_missing(self):
        """add_memory() does not raise when mem0 is not installed."""
        import mandarin.ai.memory as mem_mod

        with patch.dict("sys.modules", {"mem0": None}):
            # Should not raise
            mem_mod.add_memory("u1", "msg", "resp", "discord")

    def test_add_memory_catches_exception(self):
        """add_memory() catches and logs exceptions from mem.add()."""
        import mandarin.ai.memory as mem_mod

        mock_mem = MagicMock()
        mock_mem.add.side_effect = RuntimeError("connection lost")
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = mock_mem

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            # Should not raise
            mem_mod.add_memory("u1", "msg", "resp")


class TestSearchMemory(unittest.TestCase):
    """search_memory() retrieves relevant memories as list of dicts."""

    def setUp(self):
        _reset_memory_globals()

    def tearDown(self):
        _reset_memory_globals()

    def test_search_returns_list_from_dict_results(self):
        """When mem0 returns {results: [...]}, search_memory extracts the list."""
        import mandarin.ai.memory as mem_mod

        mock_mem = MagicMock()
        mock_mem.search.return_value = {
            "results": [
                {"memory": "user likes grammar drills"},
                {"memory": "user is HSK 3"},
            ]
        }
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = mock_mem

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            results = mem_mod.search_memory("user1", "what level am I?", limit=3)

        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["memory"], "user likes grammar drills")
        mock_mem.search.assert_called_once_with(
            "what level am I?", user_id="user1", limit=3,
        )

    def test_search_returns_list_directly(self):
        """When mem0 returns a plain list, search_memory passes it through."""
        import mandarin.ai.memory as mem_mod

        mock_mem = MagicMock()
        mock_mem.search.return_value = [{"text": "memory A"}]
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = mock_mem

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            results = mem_mod.search_memory("u2", "query")

        self.assertEqual(results, [{"text": "memory A"}])

    def test_search_returns_empty_when_mem0_missing(self):
        """search_memory() returns [] when mem0 is not installed."""
        import mandarin.ai.memory as mem_mod

        with patch.dict("sys.modules", {"mem0": None}):
            results = mem_mod.search_memory("u1", "anything")

        self.assertEqual(results, [])

    def test_search_catches_exception(self):
        """search_memory() returns [] on any runtime error."""
        import mandarin.ai.memory as mem_mod

        mock_mem = MagicMock()
        mock_mem.search.side_effect = RuntimeError("timeout")
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = mock_mem

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            results = mem_mod.search_memory("u1", "query")

        self.assertEqual(results, [])

    def test_search_handles_memories_key(self):
        """When mem0 returns {memories: [...]}, search_memory extracts it."""
        import mandarin.ai.memory as mem_mod

        mock_mem = MagicMock()
        mock_mem.search.return_value = {"memories": [{"memory": "A"}]}
        fake_mem0 = MagicMock()
        fake_mem0.Memory.from_config.return_value = mock_mem

        with patch.dict("sys.modules", {"mem0": fake_mem0}):
            results = mem_mod.search_memory("u1", "q")

        # "results" key is checked first but missing, falls back to "memories"
        self.assertEqual(results, [{"memory": "A"}])


if __name__ == "__main__":
    unittest.main()
