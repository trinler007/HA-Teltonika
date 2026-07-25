"""Regression tests for coordinator scheduling behavior."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

COORDINATOR_PATH = (
    Path(__file__).parents[1] / "custom_components" / "teltonika" / "coordinator.py"
)


class CoordinatorSchedulingTests(unittest.TestCase):
    """Guard live updates from starving scheduled API polling."""

    def test_nmea_updates_do_not_reset_refresh_interval(self) -> None:
        tree = ast.parse(COORDINATOR_PATH.read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == "_async_process_nmea"
        )
        calls = {
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertIn("_async_publish_live_data", calls)
        self.assertNotIn("async_set_updated_data", calls)


if __name__ == "__main__":
    unittest.main()
