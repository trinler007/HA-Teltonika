"""Regression tests for coordinator scheduling behavior."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

COORDINATOR_PATH = (
    Path(__file__).parents[1] / "custom_components" / "teltonika" / "coordinator.py"
)
CONFIG_FLOW_PATH = (
    Path(__file__).parents[1] / "custom_components" / "teltonika" / "config_flow.py"
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

    def test_optional_requests_are_bounded_and_time_limited(self) -> None:
        """Guard startup from a slow optional RutOS endpoint."""
        tree = ast.parse(COORDINATOR_PATH.read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_async_optional_data"
        )
        async_contexts = [
            item.context_expr
            for node in ast.walk(function)
            if isinstance(node, ast.AsyncWith)
            for item in node.items
        ]

        self.assertTrue(
            any(
                isinstance(context, ast.Attribute)
                and context.attr == "_optional_api_semaphore"
                for context in async_contexts
            )
        )
        self.assertTrue(
            any(
                isinstance(context, ast.Call)
                and isinstance(context.func, ast.Attribute)
                and context.func.attr == "timeout"
                for context in async_contexts
            )
        )

    def test_setup_does_not_use_strict_system_info_model(self) -> None:
        """Guard startup against RutOS response-schema differences."""
        tree = ast.parse(COORDINATOR_PATH.read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_async_setup"
        )

        method_calls = {
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        string_constants = {
            node.value
            for node in ast.walk(function)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

        self.assertNotIn("get_system_info", method_calls)
        self.assertIn("_async_optional_data", method_calls)
        self.assertIn("system/device/status", string_constants)

    def test_config_flow_does_not_use_strict_system_info_model(self) -> None:
        """Guard config flow fallback against RutOS response-schema differences."""
        tree = ast.parse(CONFIG_FLOW_PATH.read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "validate_input"
        )

        method_calls = {
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        string_constants = {
            node.value
            for node in ast.walk(function)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

        self.assertNotIn("get_system_info", method_calls)
        self.assertIn("request_json", method_calls)
        self.assertIn("system/device/status", string_constants)


if __name__ == "__main__":
    unittest.main()
