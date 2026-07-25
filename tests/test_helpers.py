"""Tests for Teltonika data helpers."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HELPERS_PATH = (
    Path(__file__).parents[1] / "custom_components" / "teltonika" / "helpers.py"
)
SPEC = importlib.util.spec_from_file_location("teltonika_helpers", HELPERS_PATH)
assert SPEC is not None and SPEC.loader is not None
HELPERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPERS)


class ConversionTests(unittest.TestCase):
    """Test conversion helpers."""

    def test_numeric_strings(self) -> None:
        self.assertEqual(HELPERS.as_float("52.1234"), 52.1234)
        self.assertEqual(HELPERS.as_int("12"), 12)

    def test_invalid_values(self) -> None:
        self.assertIsNone(HELPERS.as_float("N/A"))
        self.assertIsNone(HELPERS.as_int(None))


class ActiveWanTests(unittest.TestCase):
    """Test active Internet interface selection."""

    def test_failover_order_wins(self) -> None:
        interfaces = [
            {"id": "wan", "network_type": "wired", "metric": 1},
            {"id": "mob1s1a1", "network_type": "mobile", "metric": 5},
        ]
        failover = {
            "mob1s1a1": {"status": "online", "up": True},
            "wan": {"status": "offline", "up": False},
        }

        result = HELPERS.active_wan_interfaces(interfaces, failover)

        self.assertEqual([item["id"] for item in result], ["mob1s1a1"])
        self.assertEqual(result[0]["failover_status"], "online")

    def test_default_route_fallback_uses_metric(self) -> None:
        default_route = [{"target": "0.0.0.0", "mask": 0}]
        interfaces = [
            {"id": "mobile", "up": True, "metric": 5, "route": default_route},
            {"id": "wan", "up": True, "metric": 1, "route": default_route},
            {"id": "lan", "up": True, "metric": 0, "route": []},
        ]

        result = HELPERS.active_wan_interfaces(interfaces, {})

        self.assertEqual([item["id"] for item in result], ["wan", "mobile"])


if __name__ == "__main__":
    unittest.main()
