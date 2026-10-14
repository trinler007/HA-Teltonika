"""Tests for brief cellular connection summaries."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "teltonika"
    / "connection_summary.py"
)
SPEC = importlib.util.spec_from_file_location(
    "teltonika_connection_summary", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
SUMMARY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUMMARY
SPEC.loader.exec_module(SUMMARY)


class BriefConnectionSummaryTests(unittest.TestCase):
    """Test compact voice-assistant output and limit warnings."""

    def assessment(self, **values: object) -> SimpleNamespace:
        """Return a minimal connection assessment."""
        defaults = {
            "connected": True,
            "technology": "5G NSA",
            "quality": "good",
            "signal_bars": 3,
        }
        return SimpleNamespace(**(defaults | values))

    def test_home_network_summary_is_short(self) -> None:
        self.assertEqual(
            SUMMARY.describe_mobile_connection_brief(
                self.assessment(), "de-DE"
            ),
            "5G NSA: gut, 3 von 4 Balken im Heimatnetz.",
        )

    def test_roaming_and_near_limits_are_reported(self) -> None:
        description = SUMMARY.describe_mobile_connection_brief(
            self.assessment(),
            "de-DE",
            roaming=True,
            sms_limit=10,
            sms_sent=8,
            data_limit_bytes=100 * 1048576,
            data_used_bytes=75 * 1048576,
            data_warning_bytes=70 * 1048576,
        )
        self.assertIn("im Roamingnetz", description)
        self.assertIn("SMS-Limit fast erreicht", description)
        self.assertIn("Datenlimit fast erreicht", description)

    def test_reached_limits_are_reported_in_english(self) -> None:
        description = SUMMARY.describe_mobile_connection_brief(
            self.assessment(technology="4G LTE"),
            "en",
            sms_limit=10,
            sms_sent=10,
            data_limit_bytes=100,
            data_used_bytes=100,
        )
        self.assertIn("on the home network", description)
        self.assertIn("SMS limit reached", description)
        self.assertIn("data limit reached", description)

    def test_disconnected_summary(self) -> None:
        self.assertEqual(
            SUMMARY.describe_mobile_connection_brief(
                self.assessment(connected=False, signal_bars=0), "de-DE"
            ),
            "Mobilfunk: nicht verbunden, 0 von 4 Balken.",
        )


if __name__ == "__main__":
    unittest.main()
