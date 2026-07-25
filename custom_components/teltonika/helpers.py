"""Pure data helpers for the Teltonika integration."""

from __future__ import annotations

import math
from typing import Any

EARTH_RADIUS_KM = 6371.0088


def as_float(value: Any) -> float | None:
    """Convert an API value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    """Convert an API value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def distance_km(
    latitude: Any,
    longitude: Any,
    home_latitude: Any,
    home_longitude: Any,
) -> float | None:
    """Calculate the great-circle distance between two WGS84 coordinates."""
    lat = as_float(latitude)
    lon = as_float(longitude)
    home_lat = as_float(home_latitude)
    home_lon = as_float(home_longitude)
    if (
        lat is None
        or lon is None
        or home_lat is None
        or home_lon is None
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
        or not -90 <= home_lat <= 90
        or not -180 <= home_lon <= 180
    ):
        return None

    lat_delta = math.radians(home_lat - lat)
    lon_delta = math.radians(home_lon - lon)
    value = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(math.radians(lat))
        * math.cos(math.radians(home_lat))
        * math.sin(lon_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, value)))


def maidenhead_locator(latitude: Any, longitude: Any) -> str | None:
    """Return a six-character Maidenhead grid locator."""
    lat = as_float(latitude)
    lon = as_float(longitude)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None

    # The upper bounds belong to the adjacent, non-existent field. Clamp the
    # adjusted values into the final valid grid square.
    adjusted_lat = min(lat + 90.0, math.nextafter(180.0, -math.inf))
    adjusted_lon = min(lon + 180.0, math.nextafter(360.0, -math.inf))

    field_lon = int(adjusted_lon // 20)
    field_lat = int(adjusted_lat // 10)
    square_lon = int((adjusted_lon % 20) // 2)
    square_lat = int(adjusted_lat % 10)
    subsquare_lon = int(((adjusted_lon % 2) / 2) * 24)
    subsquare_lat = int((adjusted_lat % 1) * 24)

    return (
        f"{chr(ord('A') + field_lon)}{chr(ord('A') + field_lat)}"
        f"{square_lon}{square_lat}"
        f"{chr(ord('a') + subsquare_lon)}{chr(ord('a') + subsquare_lat)}"
    )


def interface_ip_address(interface: dict[str, Any]) -> str | None:
    """Return the primary IPv4 address of a network interface without CIDR."""
    for value in interface.get("ipaddrs") or []:
        if isinstance(value, str) and value:
            return value.split("/", 1)[0]
    for value in interface.get("ipv4-address") or []:
        if isinstance(value, dict) and value.get("address"):
            return str(value["address"])
    return None


def data_usage_totals(entries: Any) -> dict[str, int]:
    """Sum RX, TX and total bytes from RutOS data-usage entries."""
    rx_bytes = 0
    tx_bytes = 0
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, list) or len(entry) < 3:
                continue
            try:
                rx_bytes += max(0, int(entry[1]))
                tx_bytes += max(0, int(entry[2]))
            except (TypeError, ValueError):
                continue
    return {
        "rx": rx_bytes,
        "tx": tx_bytes,
        "total": rx_bytes + tx_bytes,
    }


def supports_sim_switch(modem: Any) -> bool:
    """Return whether a modem exposes physical SIM switching."""
    return bool(
        (getattr(modem, "sim_count", 0) or 0) >= 2
        or getattr(modem, "sim_switch_enabled", False)
    )


def is_enabled(value: Any) -> bool:
    """Return whether an API value represents an enabled flag."""
    return (
        value is True
        or value == 1
        or (isinstance(value, str) and value.lower() in {"1", "true", "yes", "on"})
    )


def is_esim_sim_card(sim_card: Any) -> bool:
    """Return whether a SIM-card configuration represents an eSIM."""
    if not isinstance(sim_card, dict):
        return False
    return bool(sim_card.get("esim_profile")) or str(
        sim_card.get("type", "")
    ).lower() in {"esim", "e-sim"}


def esim_sim_card_for_modem(
    sim_cards: list[dict[str, Any]],
    modem_id: str,
    preferred_profile: str | None = None,
) -> dict[str, Any] | None:
    """Return the best eSIM configuration to activate for a modem."""
    candidates = [
        sim_card
        for sim_card in sim_cards
        if str(sim_card.get("modem")) == modem_id and is_esim_sim_card(sim_card)
    ]
    if not candidates:
        return None
    if preferred_profile and (
        match := next(
            (
                sim_card
                for sim_card in candidates
                if str(sim_card.get("esim_profile")) == preferred_profile
            ),
            None,
        )
    ):
        return match
    return next(
        (sim_card for sim_card in candidates if is_enabled(sim_card.get("primary"))),
        candidates[0],
    )


def reverse_geocode_location_name(payload: Any) -> str | None:
    """Extract the best worldwide locality name from a geocoder response."""
    if not isinstance(payload, dict):
        return None
    address = payload.get("address")
    if not isinstance(address, dict):
        address = {}
    for key in (
        "city",
        "town",
        "village",
        "municipality",
        "hamlet",
        "suburb",
        "county",
        "state",
        "country",
    ):
        if value := address.get(key):
            return str(value)
    value = payload.get("name") or payload.get("display_name")
    return str(value) if value else None


def esim_profiles_for_modem(
    profiles: list[dict[str, Any]],
    modem_ids: list[str],
    modem_id: str,
) -> list[dict[str, Any]]:
    """Assign eSIM profiles without a modem ID when only one modem exists."""
    result = [profile for profile in profiles if str(profile.get("modem")) == modem_id]
    if len(modem_ids) == 1 and modem_ids[0] == modem_id:
        result.extend(
            profile
            for profile in profiles
            if not profile.get("modem") and profile not in result
        )
    return result


def active_wan_interfaces(
    interfaces: list[dict[str, Any]],
    failover: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return active Internet-facing interfaces in router priority order."""
    by_id = {
        str(value): interface
        for interface in interfaces
        for value in (
            interface.get("id"),
            interface.get("interface"),
            interface.get("ifname"),
        )
        if value
    }
    active: list[dict[str, Any]] = []

    for name, status in failover.items():
        if not isinstance(status, dict):
            continue
        if status.get("status") not in ("online", "notracking") and not (
            status.get("up") and status.get("running")
        ):
            continue
        interface = dict(by_id.get(name, {}))
        interface.setdefault("id", name)
        interface["failover_status"] = status.get("status")
        active.append(interface)

    if active:
        return active

    candidates = []
    for interface in interfaces:
        if not (interface.get("up") or interface.get("is_up")):
            continue
        routes = interface.get("route") or []
        has_default_route = any(
            isinstance(route, dict)
            and route.get("target") == "0.0.0.0"
            and route.get("mask") == 0
            for route in routes
        )
        if (
            has_default_route
            or interface.get("area_type") == "wan"
            or interface.get("network_type") == "mobile"
        ):
            candidates.append(interface)
    return sorted(candidates, key=lambda item: item.get("metric", 9999))
