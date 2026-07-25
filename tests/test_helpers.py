"""Tests for Teltonika data helpers."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

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


class DataUsageTests(unittest.TestCase):
    """Test RutOS traffic data aggregation."""

    def test_data_usage_totals(self) -> None:
        self.assertEqual(
            HELPERS.data_usage_totals(
                [
                    [1710000000, 100, 50],
                    [1710000060, "200", "75"],
                    ["invalid"],
                    [1710000120, "unknown", 5],
                ]
            ),
            {"rx": 300, "tx": 125, "total": 425},
        )

    def test_sim_switch_capability(self) -> None:
        self.assertTrue(
            HELPERS.supports_sim_switch(
                SimpleNamespace(sim_count=2, sim_switch_enabled=False)
            )
        )
        self.assertTrue(
            HELPERS.supports_sim_switch(
                SimpleNamespace(sim_count=1, sim_switch_enabled=True)
            )
        )
        self.assertFalse(
            HELPERS.supports_sim_switch(
                SimpleNamespace(sim_count=1, sim_switch_enabled=False)
            )
        )


class ReverseGeocodingTests(unittest.TestCase):
    """Test worldwide reverse-geocoding result extraction."""

    def test_prefers_city_and_supports_villages(self) -> None:
        self.assertEqual(
            HELPERS.reverse_geocode_location_name(
                {
                    "display_name": "Berlin, Deutschland",
                    "address": {"city": "Berlin", "country": "Deutschland"},
                }
            ),
            "Berlin",
        )
        self.assertEqual(
            HELPERS.reverse_geocode_location_name(
                {"address": {"village": "Kallista", "country": "Australia"}}
            ),
            "Kallista",
        )

    def test_falls_back_to_display_name(self) -> None:
        self.assertEqual(
            HELPERS.reverse_geocode_location_name(
                {"display_name": "Remote location, Antarctica"}
            ),
            "Remote location, Antarctica",
        )
        self.assertIsNone(HELPERS.reverse_geocode_location_name(None))


class EsimProfileTests(unittest.TestCase):
    """Test profile assignment for eSIM API variants."""

    def test_assigns_profile_without_modem_on_single_modem_router(self) -> None:
        profile = {"id": "1", "name": "Travel"}
        self.assertEqual(
            HELPERS.esim_profiles_for_modem([profile], ["1-1"], "1-1"),
            [profile],
        )

    def test_does_not_guess_with_multiple_modems(self) -> None:
        profile = {"id": "1", "name": "Travel"}
        self.assertEqual(
            HELPERS.esim_profiles_for_modem([profile], ["1-1", "2-1"], "1-1"),
            [],
        )


class LocationTests(unittest.TestCase):
    """Test calculated location helpers."""

    def test_distance_uses_great_circle(self) -> None:
        self.assertAlmostEqual(
            HELPERS.distance_km(0, 0, 0, 1),
            111.195,
            places=3,
        )
        self.assertEqual(
            HELPERS.distance_km(47.72368, 10.305336, 47.72368, 10.305336),
            0,
        )

    def test_invalid_distance_coordinates(self) -> None:
        self.assertIsNone(HELPERS.distance_km(91, 0, 0, 0))
        self.assertIsNone(HELPERS.distance_km("unknown", 0, 0, 0))

    def test_maidenhead_locator(self) -> None:
        self.assertEqual(
            HELPERS.maidenhead_locator(47.72368, 10.305336),
            "JN57dr",
        )
        self.assertEqual(HELPERS.maidenhead_locator(-90, -180), "AA00aa")
        self.assertEqual(HELPERS.maidenhead_locator(90, 180), "RR99xx")
        self.assertIsNone(HELPERS.maidenhead_locator(-91, 0))


class InterfaceTests(unittest.TestCase):
    """Test interface value extraction."""

    def test_primary_ip_without_prefix(self) -> None:
        self.assertEqual(
            HELPERS.interface_ip_address({"ipaddrs": ["10.20.30.40/32"]}),
            "10.20.30.40",
        )
        self.assertEqual(
            HELPERS.interface_ip_address(
                {"ipv4-address": [{"address": "192.0.2.5", "mask": 24}]}
            ),
            "192.0.2.5",
        )


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
