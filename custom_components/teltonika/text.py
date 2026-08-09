"""Teltonika text configuration entities."""

from __future__ import annotations

from typing import override

from homeassistant.components.text import TextEntity, TextMode
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
    """Set up active-SIM text settings."""
    async_add_entities([TeltonikaCurrentDataWarningPhone(entry.runtime_data)])


class TeltonikaCurrentDataWarningPhone(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], TextEntity
):
    """Configure the data-limit warning recipient of the active SIM."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_data_warning_phone"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = TextMode.TEXT
    _attr_native_min = 1
    _attr_native_max = 32

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_current_sim_data_warning_phone"

    @property
    @override
    def available(self) -> bool:
        config, _status = self.coordinator.active_data_limit
        return super().available and config is not None

    @property
    @override
    def native_value(self) -> str | None:
        config, _status = self.coordinator.active_data_limit
        value = config.get("warning_num") if config else None
        return str(value) if value else None

    @override
    async def async_set_value(self, value: str) -> None:
        config, _status = self.coordinator.active_data_limit
        if config is not None:
            await self.coordinator.async_update_data_limit(
                str(config["id"]), {"warning_num": value.strip()}
            )
