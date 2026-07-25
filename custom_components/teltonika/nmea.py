"""NMEA sentence parsing and TCP receiver for Teltonika GPS streams."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

KNOTS_TO_KMH = 1.852


def _as_float(value: str) -> float | None:
    """Convert a non-empty NMEA field to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coordinate(value: str, hemisphere: str) -> float | None:
    """Convert an NMEA degrees/minutes coordinate to decimal degrees."""
    raw = _as_float(value)
    if raw is None:
        return None
    degrees = int(raw // 100)
    coordinate = degrees + (raw - degrees * 100) / 60
    if hemisphere in ("S", "W"):
        coordinate = -coordinate
    return coordinate


def _payload(sentence: str) -> list[str] | None:
    """Validate a sentence checksum, when present, and return its fields."""
    sentence = sentence.strip()
    if not sentence.startswith("$"):
        return None

    body = sentence[1:]
    if "*" in body:
        body, checksum = body.split("*", 1)
        if len(checksum) < 2:
            return None
        calculated = 0
        for character in body:
            calculated ^= ord(character)
        try:
            expected = int(checksum[:2], 16)
        except ValueError:
            return None
        if calculated != expected:
            return None
    return body.split(",")


def parse_nmea_sentence(sentence: str) -> dict[str, Any] | None:
    """Parse GPS fields from a GGA or RMC NMEA sentence."""
    fields = _payload(sentence)
    if not fields:
        return None

    sentence_type = fields[0][-3:]
    update: dict[str, Any] = {}

    if sentence_type == "GGA" and len(fields) >= 10:
        latitude = _coordinate(fields[2], fields[3])
        longitude = _coordinate(fields[4], fields[5])
        if latitude is not None:
            update["latitude"] = latitude
        if longitude is not None:
            update["longitude"] = longitude

        try:
            update["fix_status"] = int(fields[6] or 0)
        except ValueError:
            pass
        try:
            update["satellites"] = int(fields[7])
        except ValueError:
            pass

        accuracy = _as_float(fields[8])
        altitude = _as_float(fields[9])
        if accuracy is not None:
            update["accuracy"] = accuracy
        if altitude is not None:
            update["altitude"] = altitude
        if fields[1]:
            update["timestamp"] = fields[1]

    elif sentence_type == "RMC" and len(fields) >= 10:
        valid = fields[2] == "A"
        update["fix_status"] = 1 if valid else 0
        speed = _as_float(fields[7])
        course = _as_float(fields[8])
        if speed is not None:
            update["speed"] = speed * KNOTS_TO_KMH
        if course is not None:
            update["angle"] = course
        if valid:
            latitude = _coordinate(fields[3], fields[4])
            longitude = _coordinate(fields[5], fields[6])
            if latitude is not None:
                update["latitude"] = latitude
            if longitude is not None:
                update["longitude"] = longitude
        if fields[1]:
            update["timestamp"] = fields[1]
        if fields[9]:
            update["date"] = fields[9]
    else:
        return None

    return update or None


class NmeaTcpServer:
    """Receive newline-delimited NMEA data over TCP."""

    def __init__(
        self,
        port: int,
        update_callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """Initialize the receiver."""
        self._port = port
        self._update_callback = update_callback
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    async def async_start(self) -> None:
        """Start listening on all IPv4 interfaces."""
        self._server = await asyncio.start_server(
            self._async_handle_connection,
            host="0.0.0.0",
            port=self._port,
            limit=4096,
        )
        _LOGGER.info("Listening for Teltonika NMEA data on TCP port %s", self._port)

    async def async_stop(self) -> None:
        """Stop listening and close active stream connections."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        writers = tuple(self._writers)
        for writer in writers:
            writer.close()
        for writer in writers:
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
        self._writers.clear()

    async def _async_handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Read NMEA sentences from one router connection."""
        self._writers.add(writer)
        peer = writer.get_extra_info("peername")
        _LOGGER.debug("NMEA stream connected from %s", peer)
        try:
            while line := await reader.readline():
                try:
                    sentence = line.decode("ascii").strip()
                except UnicodeDecodeError:
                    continue
                if update := parse_nmea_sentence(sentence):
                    self._update_callback(update)
        except (ConnectionError, ValueError) as err:
            _LOGGER.debug("NMEA stream from %s ended: %s", peer, err)
        finally:
            self._writers.discard(writer)
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
