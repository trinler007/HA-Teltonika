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
from .helpers import is_enabled, sim_card_name, sim_card_status


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Teltonika binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [TeltonikaNmeaStatusBinarySensor(coordinator)]
        + [
            TeltonikaRoamingBinarySensor(coordinator, modem_id)
            for modem_id in coordinator.data.modems
        ]
        + [
            TeltonikaSimPinLockBinarySensor(coordinator, sim_card)
            for sim_card in coordinator.data.sim_cards
        ]
    )


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


class TeltonikaRoamingBinarySensor(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], BinarySensorEntity
):
    """Show whether a modem is registered in a roaming network."""

    _attr_has_entity_name = True
    _attr_translation_key = "roaming"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, modem_id: str
    ) -> None:
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{modem_id}_roaming"
        modem = coordinator.data.modems[modem_id]
        self._attr_translation_placeholders = {
            "modem_name": modem.name or f"Modem {modem_id}"
        }

    @property
    @override
    def is_on(self) -> bool:
        modem = self.coordinator.data.modems.get(self._modem_id)
        state = (
            getattr(modem, "operator_state", None)
            or getattr(modem, "netstate", None)
            or ""
        )
        return "roaming" in str(state).lower()


class TeltonikaSimPinLockBinarySensor(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], BinarySensorEntity
):
    """Show whether PIN locking is enabled for one SIM configuration."""

    _attr_has_entity_name = True
    _attr_translation_key = "sim_pin_lock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        sim_card: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._sim_card_id = str(sim_card["id"])
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{self._sim_card_id}_sim_pin_lock"
        self._attr_translation_placeholders = {"sim_name": sim_card_name(sim_card)}

    @property
    @override
    def available(self) -> bool:
        return (
            super().available
            and sim_card_status(
                self.coordinator.data.sim_card_status, self._sim_card_id
            )
            is not None
        )

    @property
    @override
    def is_on(self) -> bool:
        status = sim_card_status(
            self.coordinator.data.sim_card_status, self._sim_card_id
        )
        return bool(status) and is_enabled(status.get("pin_lock_enabled"))
