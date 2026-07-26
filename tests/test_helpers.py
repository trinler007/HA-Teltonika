"""Tests for Teltonika data helpers."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

HELPERS_PATH = (
    Path(__file__).parents[1] / "custom_components" / "teltonika" / "helpers.py"
)
SPEC = importlib.util.spec_from_file_location("teltonika_helpers", HELPERS_PATH)
assert SPEC is not None and SPEC.loader is not None
HELPERS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HELPERS
SPEC.loader.exec_module(HELPERS)


class ConversionTests(unittest.TestCase):
    """Test conversion helpers."""

    def test_numeric_strings(self) -> None:
        self.assertEqual(HELPERS.as_float("52.1234"), 52.1234)
        self.assertEqual(HELPERS.as_int("12"), 12)

    def test_invalid_values(self) -> None:
        self.assertIsNone(HELPERS.as_float("N/A"))
        self.assertIsNone(HELPERS.as_int(None))


class MobileConnectionAssessmentTests(unittest.TestCase):
    """Test radio quality and capacity estimation."""

    def test_signal_bar_boundaries(self) -> None:
        self.assertEqual(HELPERS._signal_bars(False, 100), 0)
        self.assertIsNone(HELPERS._signal_bars(True, None))
        self.assertEqual(HELPERS._signal_bars(True, 24), 1)
        self.assertEqual(HELPERS._signal_bars(True, 25), 2)
        self.assertEqual(HELPERS._signal_bars(True, 49), 2)
        self.assertEqual(HELPERS._signal_bars(True, 50), 3)
        self.assertEqual(HELPERS._signal_bars(True, 74), 3)
        self.assertEqual(HELPERS._signal_bars(True, 75), 4)

    def test_5g_nsa_carrier_aggregation(self) -> None:
        modem = SimpleNamespace(
            conntype="5G (NSA)",
            data_conn_state="Connected",
            operator_state="Registered, home",
            rsrp=-86,
            rsrq=-7,
            sinr=13,
            rssi=-58,
            band="5G N78",
            ca_signal=[
                SimpleNamespace(band="LTE B1", bandwidth="20", nr_arfcn=None),
                SimpleNamespace(band="LTE B7", bandwidth="20", nr_arfcn=None),
                SimpleNamespace(band="LTE B20", bandwidth="10", nr_arfcn=None),
                SimpleNamespace(band="5G N78", bandwidth="80", nr_arfcn=631968),
            ],
            cell_info=[],
        )

        result = HELPERS.assess_mobile_connection(modem)

        self.assertTrue(result.connected)
        self.assertEqual(result.technology, "5G NSA")
        self.assertEqual(result.quality, "very_good")
        self.assertEqual(result.signal_bars, 4)
        self.assertEqual(result.carrier_count, 4)
        self.assertEqual(result.total_bandwidth_mhz, 130)
        self.assertEqual(result.radio_ceiling_mbps, 2440)
        self.assertGreater(result.estimated_high_mbps, result.estimated_low_mbps)
        self.assertEqual(result.confidence, "high")

        description = HELPERS.describe_mobile_connection(result, "de-DE")
        self.assertIn("5G NSA", description)
        self.assertIn("4 Träger", description)
        self.assertIn("RSRP -86 dBm ausgezeichnet", description)
        self.assertIn("SINR 13 dB gut", description)
        self.assertIn("Megabit pro Sekunde", description)
        self.assertLessEqual(len(description), 255)
        self.assertLessEqual(len(HELPERS.describe_mobile_connection(result, "en")), 255)

    def test_disconnected_modem_has_no_capacity(self) -> None:
        modem = SimpleNamespace(
            conntype="LTE",
            data_conn_state="Disconnected",
            operator_state="Registered, home",
            ca_signal=[],
            cell_info=[],
            band=None,
        )

        result = HELPERS.assess_mobile_connection(modem)

        self.assertFalse(result.connected)
        self.assertEqual(result.quality, "disconnected")
        self.assertEqual(result.signal_bars, 0)
        self.assertIsNone(result.estimated_high_mbps)
        self.assertEqual(
            HELPERS.describe_mobile_connection(result, "en"),
            "The cellular connection is currently disconnected.",
        )

    def test_single_lte_carrier_uses_serving_cell_bandwidth(self) -> None:
        modem = SimpleNamespace(
            conntype="4G LTE",
            data_conn_state="Connected",
            operator_state="Registered, roaming",
            rsrp=-105,
            rsrq=-14,
            sinr=2,
            rssi=-80,
            ca_signal=[],
            cell_info=[SimpleNamespace(band=None, bandwidth="20", nr_arfcn="N/A")],
            band="LTE B20",
        )

        result = HELPERS.assess_mobile_connection(modem)

        self.assertEqual(result.technology, "4G LTE")
        self.assertEqual(result.total_bandwidth_mhz, 20)
        self.assertEqual(result.radio_ceiling_mbps, 400)
        self.assertEqual(result.signal_bars, 2)
        self.assertEqual(result.carrier_count, 1)
        self.assertEqual(result.bands, ("LTE B20",))


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

    def test_sim_switch_waits_for_target_and_setup_complete(self) -> None:
        modem = SimpleNamespace(
            active_sim=2,
            esim_profile=None,
            mobile_stage=18,
            operator="Telekom.de",
            operator_state="registered",
        )
        self.assertFalse(
            HELPERS.modem_sim_switch_complete(
                modem,
                2,
                expect_esim=False,
            )
        )
        modem.mobile_stage = 19
        self.assertTrue(
            HELPERS.modem_sim_switch_complete(
                modem,
                2,
                expect_esim=False,
            )
        )
        self.assertFalse(
            HELPERS.modem_sim_switch_complete(
                modem,
                1,
                expect_esim=False,
            )
        )

    def test_sim_switch_distinguishes_physical_sim_and_esim(self) -> None:
        modem = SimpleNamespace(
            active_sim=2,
            esim_profile="1",
            mobile_stage=None,
            operator="o2 - de",
            operator_state="registered",
        )
        self.assertTrue(
            HELPERS.modem_sim_switch_complete(
                modem,
                2,
                expect_esim=True,
            )
        )
        self.assertFalse(
            HELPERS.modem_sim_switch_complete(
                modem,
                2,
                expect_esim=False,
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

    def test_identifies_and_selects_esim_sim_card(self) -> None:
        sim_cards = [
            {"id": "sim1", "modem": "1-1", "position": "1", "primary": "1"},
            {
                "id": "esim1",
                "modem": "1-1",
                "position": "2",
                "esim_profile": "1",
                "primary": "0",
            },
            {
                "id": "esim2",
                "modem": "1-1",
                "position": "2",
                "esim_profile": "2",
                "primary": "0",
            },
        ]

        self.assertFalse(HELPERS.is_esim_sim_card(sim_cards[0]))
        self.assertTrue(HELPERS.is_esim_sim_card(sim_cards[1]))
        self.assertEqual(
            HELPERS.esim_sim_card_for_modem(sim_cards, "1-1", "2")["id"],
            "esim2",
        )

    def test_prefers_default_esim_and_handles_missing_modem(self) -> None:
        sim_cards = [
            {
                "id": "esim1",
                "modem": "1-1",
                "esim_profile": "1",
                "primary": "0",
            },
            {
                "id": "esim2",
                "modem": "1-1",
                "esim_profile": "2",
                "primary": "1",
            },
        ]

        self.assertEqual(
            HELPERS.esim_sim_card_for_modem(sim_cards, "1-1")["id"],
            "esim2",
        )
        self.assertIsNone(HELPERS.esim_sim_card_for_modem(sim_cards, "2-1"))

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
