"""Tests for persisted route closures."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from closures import ClosureStore
from main import confirm_saved_closures_in_terminal


class ClosureStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "baustellen.json"
        self.store = ClosureStore(self.path, {1: [0, 1, 2, 3]})

    def test_set_and_load_closure(self):
        self.store.set(1, (1, 2))
        loaded = ClosureStore(self.path, {1: [0, 1, 2, 3]})

        self.assertEqual(loaded.load(), {1: (1, 2)})
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")),
            {"closures": {"1": [1, 2]}},
        )

    def test_remove_persists_empty_state(self):
        self.store.set(1, (1, 2))
        self.store.set(1, None)

        self.assertEqual(self.store.load(), {})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"closures": {}})

    def test_accepts_closure_spanning_multiple_station_segments(self):
        self.store.set(1, (0, 3))

        self.assertEqual(self.store.get(1), (0, 3))

    def test_rejects_same_station_as_both_endpoints(self):
        with self.assertRaisesRegex(ValueError, "müssen verschieden sein"):
            self.store.set(1, (1, 1))

    def test_load_accepts_closure_spanning_multiple_station_segments(self):
        self.path.write_text(
            json.dumps({"closures": {"1": [0, 3]}}),
            encoding="utf-8",
        )

        self.assertEqual(self.store.load(), {1: (0, 3)})

    def test_load_rejects_same_station_as_both_endpoints(self):
        self.path.write_text(
            json.dumps({"closures": {"1": [1, 1]}}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "müssen verschieden sein"):
            self.store.load()

    def test_terminal_confirmation_can_remove_saved_closure(self):
        self.store.set(1, (1, 2))
        route = SimpleNamespace(
            id=1,
            name="Linie 1",
            station_names={1: "Stadttheater", 2: "Bertoldsbrunnen"},
            set_closed_section=MagicMock(),
        )

        with patch("builtins.input", return_value="n"):
            confirm_saved_closures_in_terminal([route], self.store)

        self.assertIsNone(self.store.get(1))
        route.set_closed_section.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
