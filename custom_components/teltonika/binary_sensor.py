"""Teltonika binary sensors."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Teltonika binary sensors."""
    async_add_entities([TeltonikaNmeaStatusBinarySensor(entry.runtime_data)])


class TeltonikaNmeaStatusBinarySensor(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], BinarySensorEntity
):
    """Show whether the optional NMEA TCP source is healthy."""

    _attr_has_entity_name = True
    _attr_translation_key = "nmea_tcp_status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        """Initialize the NMEA status sensor."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_nmea_tcp_status"

    @property
    @override
    def is_on(self) -> bool:
        """Return whether the stream is connected or recently active."""
        return self.coordinator.nmea_status

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return NMEA receiver diagnostics."""
        last_received = self.coordinator.nmea_last_received
        return {
            "enabled": self.coordinator.nmea_enabled,
            "connected": self.coordinator.nmea_connected,
            "port": self.coordinator.nmea_port,
            "last_received": (
                last_received.isoformat() if last_received is not None else None
            ),
        }
