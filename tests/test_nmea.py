"""Tests for NMEA GPS parsing."""

from __future__ import annotations

import asyncio
import importlib.util
import unittest
from pathlib import Path

NMEA_PATH = Path(__file__).parents[1] / "custom_components" / "teltonika" / "nmea.py"
SPEC = importlib.util.spec_from_file_location("teltonika_nmea", NMEA_PATH)
assert SPEC is not None and SPEC.loader is not None
NMEA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NMEA)


class NmeaParserTests(unittest.TestCase):
    """Test Teltonika-compatible NMEA parsing."""

    def test_gga_position_and_fix(self) -> None:
        result = NMEA.parse_nmea_sentence(
            "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
        )

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["latitude"], 48.1173)
        self.assertAlmostEqual(result["longitude"], 11.5166667)
        self.assertEqual(result["fix_status"], 1)
        self.assertEqual(result["satellites"], 8)
        self.assertEqual(result["accuracy"], 0.9)
        self.assertEqual(result["altitude"], 545.4)

    def test_rmc_speed_course_and_talker_id(self) -> None:
        result = NMEA.parse_nmea_sentence(
            "$GNRMC,092751.000,A,5321.6802,N,00630.3372,W,10.50,31.66,280511,,,A"
        )

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["latitude"], 53.3613367)
        self.assertAlmostEqual(result["longitude"], -6.50562)
        self.assertAlmostEqual(result["speed"], 19.446)
        self.assertEqual(result["angle"], 31.66)
        self.assertEqual(result["fix_status"], 1)

    def test_invalid_fix_and_checksum(self) -> None:
        invalid_fix = NMEA.parse_nmea_sentence(
            "$GPRMC,092751.000,V,,,,,0.00,,280511,,,N"
        )
        self.assertEqual(invalid_fix["fix_status"], 0)
        self.assertEqual(invalid_fix["speed"], 0)
        self.assertIsNone(
            NMEA.parse_nmea_sentence(
                "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*00"
            )
        )

    def test_unsupported_sentence(self) -> None:
        self.assertIsNone(NMEA.parse_nmea_sentence("$GPGSV,1,1,00,0"))


class NmeaTcpServerTests(unittest.IsolatedAsyncioTestCase):
    """Test live TCP updates and connection status callbacks."""

    async def test_connection_and_sentence_callbacks(self) -> None:
        updates = []
        connections = []
        server = NMEA.NmeaTcpServer(0, updates.append, connections.append)
        await server.async_start()
        self.addAsyncCleanup(server.async_stop)
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]

        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.01)
        self.assertTrue(server.connected)
        self.assertEqual(connections, [True])

        writer.write(
            b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n"
        )
        await writer.drain()
        await asyncio.sleep(0.01)
        self.assertEqual(updates[0]["satellites"], 8)

        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.01)
        self.assertFalse(server.connected)
        self.assertEqual(connections, [True, False])


if __name__ == "__main__":
    unittest.main()
