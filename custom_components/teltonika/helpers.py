"""Pure data helpers for the Teltonika integration."""

from __future__ import annotations

from typing import Any


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
