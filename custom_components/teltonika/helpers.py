"""Pure data helpers for the Teltonika integration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class MobileConnectionAssessment:
    """Calculated cellular quality and plausible peak capacity."""

    connected: bool
    technology: str
    quality: str
    quality_score: int | None
    signal_bars: int | None
    limiting_factor: str | None
    metrics: tuple[tuple[str, float, int], ...]
    carrier_count: int
    bands: tuple[str, ...]
    total_bandwidth_mhz: float | None
    estimated_low_mbps: int | None
    estimated_high_mbps: int | None
    radio_ceiling_mbps: int | None
    confidence: str


def _interpolated_score(
    value: Any, points: tuple[tuple[float, float], ...]
) -> float | None:
    """Map a radio measurement to a score from zero to one hundred."""
    numeric = as_float(value)
    if numeric is None:
        return None
    if numeric <= points[0][0]:
        return points[0][1]
    if numeric >= points[-1][0]:
        return points[-1][1]
    for (low_value, low_score), (high_value, high_score) in pairwise(points):
        if low_value <= numeric <= high_value:
            fraction = (numeric - low_value) / (high_value - low_value)
            return low_score + fraction * (high_score - low_score)
    return None


def _radio_metrics(
    modem: Any,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return raw cellular measurements and their normalized scores."""
    definitions = {
        "rsrp": ((-120, 0), (-110, 25), (-100, 50), (-90, 75), (-80, 100)),
        "rsrq": ((-20, 0), (-15, 40), (-10, 75), (-7, 100)),
        "sinr": ((-5, 0), (0, 25), (10, 60), (20, 85), (30, 100)),
        "rssi": ((-110, 0), (-95, 30), (-85, 55), (-75, 80), (-65, 100)),
    }
    values = {
        name: value
        for name in definitions
        if (value := as_float(getattr(modem, name, None))) is not None
    }
    scores = {
        name: score
        for name, points in definitions.items()
        if name in values
        and (score := _interpolated_score(values[name], points)) is not None
    }
    return values, scores


def _quality_from_score(score: float | None) -> str:
    """Return a stable quality key for a normalized score."""
    if score is None:
        return "unknown"
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "very_good"
    if score >= 55:
        return "good"
    if score >= 40:
        return "fair"
    return "poor"


def _signal_bars(connected: bool, quality_score: int | None) -> int | None:
    """Convert zero-to-100 signal quality to zero-to-four bars."""
    if not connected:
        return 0
    if quality_score is None:
        return None
    if quality_score < 25:
        return 1
    if quality_score < 50:
        return 2
    if quality_score < 75:
        return 3
    return 4


def _connection_technology(modem: Any) -> str:
    """Return a normalized, readable radio access technology."""
    value = str(
        getattr(modem, "conntype", None) or getattr(modem, "ntype", None) or "Mobilfunk"
    )
    normalized = value.lower().replace("_", " ").replace("-", " ")
    if "5g" in normalized and "nsa" in normalized:
        return "5G NSA"
    if "5g" in normalized and "sa" in normalized:
        return "5G SA"
    if "5g" in normalized:
        return "5G"
    if "lte" in normalized or "4g" in normalized:
        return "4G LTE"
    if "3g" in normalized or "umts" in normalized or "wcdma" in normalized:
        return "3G"
    if "2g" in normalized or "gsm" in normalized:
        return "2G"
    return value


def _carrier_values(modem: Any) -> list[Any]:
    """Return CA carriers, falling back to serving-cell information."""
    carriers = list(getattr(modem, "ca_signal", None) or [])
    return carriers or list(getattr(modem, "cell_info", None) or [])


def _is_nr_carrier(carrier: Any, technology: str) -> bool:
    """Return whether a carrier is a 5G NR carrier."""
    band = str(getattr(carrier, "band", "") or "").lower()
    if "5g" in band or " nr" in f" {band}" or band.startswith("n"):
        return True
    nr_arfcn = getattr(carrier, "nr_arfcn", None)
    if nr_arfcn not in (None, "", "N/A"):
        return True
    return technology in {"5G", "5G SA"} and not band


def assess_mobile_connection(modem: Any) -> MobileConnectionAssessment:
    """Estimate radio quality and plausible peak download capacity.

    The result describes radio-link potential. It intentionally does not claim
    to predict current throughput because cell load, provider policy, backhaul,
    and protocol overhead are not available from the modem status endpoint.
    """
    technology = _connection_technology(modem)
    state = str(getattr(modem, "data_conn_state", "") or "").lower()
    registered = str(getattr(modem, "operator_state", "") or "").lower()
    connected = (
        not state or ("connected" in state and "disconnected" not in state)
    ) and (
        not registered
        or (
            "registered" in registered
            and "not registered" not in registered
            and "unregistered" not in registered
        )
    )

    metric_values, metrics = _radio_metrics(modem)
    weighted_metrics = [
        (metrics[name], weight)
        for name, weight in (("rsrp", 0.35), ("rsrq", 0.25), ("sinr", 0.40))
        if name in metrics
    ]
    if not weighted_metrics and "rssi" in metrics:
        weighted_metrics = [(metrics["rssi"], 1.0)]
    quality_score = (
        round(
            sum(score * weight for score, weight in weighted_metrics)
            / sum(weight for _, weight in weighted_metrics)
        )
        if weighted_metrics
        else None
    )
    if not connected:
        quality = "disconnected"
    else:
        quality = _quality_from_score(quality_score)

    limiting_factor = min(metrics, key=metrics.get) if metrics else None
    metric_assessments = tuple(
        (name, metric_values[name], round(score)) for name, score in metrics.items()
    )
    carriers = _carrier_values(modem)
    bands = tuple(
        dict.fromkeys(
            str(band)
            for carrier in carriers
            if (band := getattr(carrier, "band", None))
        )
    )
    if not bands and (primary_band := getattr(modem, "band", None)):
        bands = (str(primary_band),)

    bandwidths: list[tuple[float, bool]] = []
    for carrier in carriers:
        bandwidth = as_float(getattr(carrier, "bandwidth", None))
        if bandwidth is not None and bandwidth > 0:
            bandwidths.append((bandwidth, _is_nr_carrier(carrier, technology)))
    total_bandwidth = (
        round(sum(bandwidth for bandwidth, _ in bandwidths), 1) if bandwidths else None
    )

    hardware_cap = 42
    assumed_ceiling = 42.0
    if technology == "5G NSA":
        hardware_cap = 3300
        assumed_ceiling = 1500.0
    elif technology in {"5G", "5G SA"}:
        hardware_cap = 2100
        assumed_ceiling = 1800.0
    elif technology == "4G LTE":
        hardware_cap = 2000
        assumed_ceiling = 400.0
    elif technology == "2G":
        hardware_cap = 1
        assumed_ceiling = 0.3

    if bandwidths:
        # Approximate the radio ceiling from occupied spectrum. The constants
        # assume the modem's best supported MIMO/modulation and are capped by
        # the published RUTX50 modem limits.
        raw_ceiling = sum(
            bandwidth * (18 if is_nr else 20) for bandwidth, is_nr in bandwidths
        )
        radio_ceiling = min(float(hardware_cap), raw_ceiling)
    else:
        radio_ceiling = min(float(hardware_cap), assumed_ceiling)

    if connected and quality_score is not None:
        upper_factor = 0.25 + 0.007 * quality_score
        estimated_high = max(1, round(radio_ceiling * upper_factor / 10) * 10)
        estimated_low = max(1, round(estimated_high * 0.45 / 10) * 10)
    else:
        estimated_low = estimated_high = None

    if bandwidths and len(metrics) >= 2:
        confidence = "high"
    elif bandwidths or metrics:
        confidence = "medium"
    else:
        confidence = "low"

    return MobileConnectionAssessment(
        connected=connected,
        technology=technology,
        quality=quality,
        quality_score=quality_score,
        signal_bars=_signal_bars(connected, quality_score),
        limiting_factor=limiting_factor,
        metrics=metric_assessments,
        carrier_count=len(carriers) or (1 if bands else 0),
        bands=bands,
        total_bandwidth_mhz=total_bandwidth,
        estimated_low_mbps=estimated_low,
        estimated_high_mbps=estimated_high,
        radio_ceiling_mbps=round(radio_ceiling),
        confidence=confidence,
    )


def describe_mobile_connection(
    assessment: MobileConnectionAssessment, language: str
) -> str:
    """Render a concise voice-assistant-friendly connection description."""
    german = language.lower().startswith("de")
    if not assessment.connected:
        return (
            "Die Mobilfunkverbindung ist derzeit nicht verbunden."
            if german
            else "The cellular connection is currently disconnected."
        )

    quality_labels = {
        "de": {
            "excellent": "ausgezeichnet",
            "very_good": "sehr gut",
            "good": "gut",
            "fair": "mäßig",
            "poor": "schlecht",
            "unknown": "nicht sicher bewertbar",
        },
        "en": {
            "excellent": "excellent",
            "very_good": "very good",
            "good": "good",
            "fair": "fair",
            "poor": "poor",
            "unknown": "not reliably assessable",
        },
    }
    locale = "de" if german else "en"
    quality = quality_labels[locale][assessment.quality]
    shown_bands = ", ".join(assessment.bands[:4])
    if len(assessment.bands) > 4:
        shown_bands += f" +{len(assessment.bands) - 4}"

    if german:
        bars_text = (
            f"{assessment.signal_bars} von 4 Balken"
            if assessment.signal_bars is not None
            else "Balken nicht bewertbar"
        )
        parts = [(f"{assessment.technology}: {quality}, {bars_text}.")]
        if assessment.carrier_count:
            carrier_text = f"{assessment.carrier_count} Träger" + (
                f" auf {shown_bands}" if shown_bands else ""
            )
            if assessment.total_bandwidth_mhz is not None:
                carrier_text += f" mit {assessment.total_bandwidth_mhz:g} Megahertz"
            parts.append(f"{carrier_text}.")
        shown_metrics = [
            (name, value, score)
            for name, value, score in assessment.metrics
            if name in {"rsrp", "rsrq", "sinr"}
        ] or list(assessment.metrics)
        if shown_metrics:
            metric_text = "; ".join(
                f"{name.upper()} {value:g} "
                f"{'dBm' if name in {'rsrp', 'rssi'} else 'dB'} "
                f"{quality_labels[locale][_quality_from_score(score)]}"
                for name, value, score in shown_metrics
            )
            parts.append(f"{metric_text}.")
        if assessment.estimated_low_mbps is not None:
            parts.append(
                "Downloadpotenzial bei geringer Last: "
                f"{assessment.estimated_low_mbps} bis "
                f"{assessment.estimated_high_mbps} Megabit pro Sekunde."
            )
        return " ".join(parts)

    bars_text = (
        f"{assessment.signal_bars} out of 4 bars"
        if assessment.signal_bars is not None
        else "bars unavailable"
    )
    parts = [f"{assessment.technology}: {quality}, {bars_text}."]
    if assessment.carrier_count:
        carrier_text = f"{assessment.carrier_count} carriers" + (
            f" on {shown_bands}" if shown_bands else ""
        )
        if assessment.total_bandwidth_mhz is not None:
            carrier_text += f" using {assessment.total_bandwidth_mhz:g} megahertz"
        parts.append(f"{carrier_text}.")
    shown_metrics = [
        (name, value, score)
        for name, value, score in assessment.metrics
        if name in {"rsrp", "rsrq", "sinr"}
    ] or list(assessment.metrics)
    if shown_metrics:
        metric_text = "; ".join(
            f"{name.upper()} {value:g} "
            f"{'dBm' if name in {'rsrp', 'rssi'} else 'dB'} "
            f"{quality_labels[locale][_quality_from_score(score)]}"
            for name, value, score in shown_metrics
        )
        parts.append(f"{metric_text}.")
    if assessment.estimated_low_mbps is not None:
        parts.append(
            "Download potential with low cell load: "
            f"{assessment.estimated_low_mbps} to "
            f"{assessment.estimated_high_mbps} megabits per second."
        )
    return " ".join(parts)


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


def compass_direction(course: Any, language: str) -> str | None:
    """Convert a course in degrees to a localized 16-point compass direction."""
    degrees = as_float(course)
    if degrees is None or not math.isfinite(degrees):
        return None
    directions = (
        (
            "N",
            "NNO",
            "NO",
            "ONO",
            "O",
            "OSO",
            "SO",
            "SSO",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        )
        if language.lower().startswith("de")
        else (
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        )
    )
    index = int(((degrees % 360) + 11.25) // 22.5) % len(directions)
    return directions[index]


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


def system_cpu_usage(system_usage: dict[str, Any]) -> float | None:
    """Return RutOS CPU utilization as a percentage."""
    value = as_float(system_usage.get("loadavg"))
    if value is None:
        return None
    return min(100.0, max(0.0, value * 100))


def system_memory_usage(system_usage: dict[str, Any]) -> float | None:
    """Return RutOS RAM utilization as a percentage."""
    memory = system_usage.get("memory")
    if not isinstance(memory, dict):
        return None
    percentage = as_float(memory.get("ram_percentage"))
    if percentage is not None:
        return min(100.0, max(0.0, percentage))
    used = as_float(memory.get("ram_used"))
    total = as_float(memory.get("ram_total"))
    if used is None or total is None or total <= 0:
        return None
    return min(100.0, max(0.0, used / total * 100))


def supports_sim_switch(modem: Any) -> bool:
    """Return whether a modem exposes physical SIM switching."""
    return bool(
        (getattr(modem, "sim_count", 0) or 0) >= 2
        or getattr(modem, "sim_switch_enabled", False)
    )


def modem_sim_switch_complete(
    modem: Any,
    expected_sim: int,
    *,
    expect_esim: bool,
) -> bool:
    """Return whether RutOS reports the selected SIM fully initialized."""
    if getattr(modem, "active_sim", None) != expected_sim:
        return False
    if bool(getattr(modem, "esim_profile", None)) != expect_esim:
        return False

    mobile_stage = as_int(getattr(modem, "mobile_stage", None))
    if mobile_stage is not None:
        # RutOS mobile stage 19 is "Setup complete".
        return mobile_stage == 19

    # Older API variants may not expose mobile_stage. In that case, wait until
    # registration data for the newly active SIM has become available.
    return bool(
        getattr(modem, "operator", None) or getattr(modem, "operator_state", None)
    )


def is_enabled(value: Any) -> bool:
    """Return whether an API value represents an enabled flag."""
    return (
        value is True
        or value == 1
        or (isinstance(value, str) and value.lower() in {"1", "true", "yes", "on"})
    )


def is_esim_profile_active(profile: Any) -> bool:
    """Return whether RutOS reports an eSIM profile as active."""
    if not isinstance(profile, dict):
        return False
    # Current RutOS versions expose the state as profile_set. Keep enabled as
    # a fallback for older API variants.
    if "profile_set" in profile:
        return is_enabled(profile.get("profile_set"))
    return is_enabled(profile.get("enabled"))


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


def interface_identifier(interface: dict[str, Any]) -> str | None:
    """Return a stable identifier for a RutOS network interface."""
    for key in ("id", "interface", "ifname", "name", "device"):
        if value := interface.get(key):
            return str(value)
    return None


def _interface_counter(interface: dict[str, Any], direction: str) -> int | None:
    """Return an RX or TX byte counter across RutOS response variants."""
    keys = (f"{direction}_bytes", f"{direction}bytes")
    sources = [
        interface,
        interface.get("statistics"),
        interface.get("stats"),
        interface.get("data"),
    ]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = as_int(source.get(key))
            if value is not None and value >= 0:
                return value
    return None


def interface_counter_snapshot(
    interfaces: list[dict[str, Any]],
) -> dict[str, tuple[int | None, int | None]]:
    """Return RX/TX counter snapshots keyed by interface identity."""
    return {
        identifier: (
            _interface_counter(interface, "rx"),
            _interface_counter(interface, "tx"),
        )
        for interface in interfaces
        if (identifier := interface_identifier(interface)) is not None
    }


def _is_lan_interface(interface: dict[str, Any]) -> bool:
    """Return whether a RutOS interface belongs to the LAN side."""
    identifier = (interface_identifier(interface) or "").lower()
    area = str(
        interface.get("area_type")
        or interface.get("zone")
        or interface.get("role")
        or ""
    ).lower()
    network_type = str(interface.get("network_type") or "").lower()
    return (
        area == "lan"
        or network_type == "lan"
        or identifier == "lan"
        or identifier.startswith(("lan", "br-lan"))
    )


def interface_transfer_rates(
    interfaces: list[dict[str, Any]],
    failover: dict[str, dict[str, Any]],
    previous: dict[str, tuple[int | None, int | None]],
    elapsed_seconds: float | None,
) -> tuple[
    dict[str, float | None],
    dict[str, tuple[int | None, int | None]],
    dict[str, list[str]],
]:
    """Calculate current WAN/LAN transfer rates from interface byte counters."""
    current = interface_counter_snapshot(interfaces)
    wan_ids = {
        identifier
        for interface in active_wan_interfaces(interfaces, failover)
        if (identifier := interface_identifier(interface)) is not None
    }
    lan_ids = {
        identifier
        for interface in interfaces
        if _is_lan_interface(interface)
        and (identifier := interface_identifier(interface)) is not None
    }
    groups = {
        "internet": sorted(wan_ids),
        "lan": sorted(lan_ids),
    }

    def _rate(interface_ids: set[str], counter_index: int) -> float | None:
        if not elapsed_seconds or elapsed_seconds <= 0:
            return None
        delta_bytes = 0
        valid_counters = 0
        for identifier in interface_ids:
            current_counter = current.get(identifier, (None, None))[counter_index]
            previous_counter = previous.get(identifier, (None, None))[counter_index]
            if (
                current_counter is None
                or previous_counter is None
                or current_counter < previous_counter
            ):
                continue
            delta_bytes += current_counter - previous_counter
            valid_counters += 1
        if not valid_counters:
            return None
        return round(delta_bytes * 8 / elapsed_seconds / 1_000_000, 6)

    return (
        {
            "internet_rx": _rate(wan_ids, 0),
            "internet_tx": _rate(wan_ids, 1),
            "lan_rx": _rate(lan_ids, 0),
            "lan_tx": _rate(lan_ids, 1),
        },
        current,
        groups,
    )
