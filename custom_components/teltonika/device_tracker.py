"""Teltonika GPS device tracker."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import as_float


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the GPS tracker."""
    async_add_entities([TeltonikaGpsTracker(entry.runtime_data)])


class TeltonikaGpsTracker(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], TrackerEntity
):
    """Represent the router position on the Home Assistant map."""

    _attr_has_entity_name = True
    _attr_translation_key = "gps_location"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        """Initialize the GPS tracker."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_gps_location"

    @property
    @override
    def available(self) -> bool:
        """Return whether valid coordinates are available."""
        gps = self.coordinator.data.gps
        return (
            super().available
            and gps is not None
            and as_float(gps.get("latitude")) is not None
            and as_float(gps.get("longitude")) is not None
        )

    @property
    @override
    def latitude(self) -> float | None:
        """Return latitude."""
        return as_float((self.coordinator.data.gps or {}).get("latitude"))

    @property
    @override
    def longitude(self) -> float | None:
        """Return longitude."""
        return as_float((self.coordinator.data.gps or {}).get("longitude"))

    @property
    @override
    def location_accuracy(self) -> int:
        """Return GPS accuracy when it is an absolute distance."""
        # Teltonika reports HDOP here, not meters. Home Assistant's tracker
        # requires meters, so avoid presenting HDOP as a false distance.
        return 0

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return GPS metadata."""
        gps = self.coordinator.data.gps or {}
        return {
            "altitude": as_float(gps.get("altitude")),
            "satellites": gps.get("satellites"),
            "hdop": as_float(gps.get("accuracy")),
            "speed": as_float(gps.get("speed")),
            "course": as_float(gps.get("angle")),
            "fix_status": gps.get("fix_status"),
            "timestamp": gps.get("utc_timestamp") or gps.get("timestamp"),
        }
