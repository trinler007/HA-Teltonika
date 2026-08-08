"""Teltonika numeric SIM configuration entities."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import as_int, sim_card_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SMS limit number entities."""
    async_add_entities(
        TeltonikaSmsLimitNumber(entry.runtime_data, sim_card)
        for sim_card in entry.runtime_data.data.sim_cards
    )


class TeltonikaSmsLimitNumber(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], NumberEntity
):
    """Configure the maximum sent SMS count for one SIM."""

    _attr_has_entity_name = True
    _attr_translation_key = "sms_limit_count"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 1000000
    _attr_native_step = 1

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, sim_card: dict[str, Any]
    ) -> None:
        super().__init__(coordinator)
        self._sim_card_id = str(sim_card["id"])
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{self._sim_card_id}_sms_limit_count"
        self._attr_translation_placeholders = {"sim_name": sim_card_name(sim_card)}

    @property
    def _config(self) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.coordinator.data.sim_cards
                if str(item.get("id")) == self._sim_card_id
            ),
            None,
        )

    @property
    @override
    def native_value(self) -> float | None:
        config = self._config
        return as_int(config.get("sms_limit_num")) if config else None

    @override
    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_sim_card(
            self._sim_card_id, {"sms_limit_num": str(round(value))}
        )
