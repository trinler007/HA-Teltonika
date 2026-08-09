"""Teltonika numeric SIM configuration entities."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfInformation
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
    async_add_entities(
        [
            TeltonikaCurrentSmsLimitNumber(entry.runtime_data),
            TeltonikaCurrentDataLimitNumber(entry.runtime_data),
            TeltonikaCurrentDataWarningNumber(entry.runtime_data),
        ]
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


class TeltonikaCurrentNumber(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], NumberEntity
):
    """Base class for a number routed to the active SIM."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_step = 1

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, suffix: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_current_sim_{suffix}"


class TeltonikaCurrentSmsLimitNumber(TeltonikaCurrentNumber):
    """Configure the SMS limit of the active SIM."""

    _attr_translation_key = "current_sms_limit_count"
    _attr_native_max_value = 1000000

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "sms_limit_count")

    @property
    @override
    def available(self) -> bool:
        return super().available and self.coordinator.active_sim_card is not None

    @property
    @override
    def native_value(self) -> float | None:
        config = self.coordinator.active_sim_card or {}
        return as_int(config.get("sms_limit_num"))

    @override
    async def async_set_native_value(self, value: float) -> None:
        config = self.coordinator.active_sim_card
        if config is not None:
            await self.coordinator.async_update_sim_card(
                str(config["id"]), {"sms_limit_num": str(round(value))}
            )


class TeltonikaCurrentDataLimitConfigNumber(TeltonikaCurrentNumber):
    """Base class for active data-limit numeric configuration."""

    config_key: str
    _attr_native_max_value = 100000000

    @property
    @override
    def available(self) -> bool:
        config, _status = self.coordinator.active_data_limit
        return super().available and config is not None

    @property
    @override
    def native_value(self) -> float | None:
        config, _status = self.coordinator.active_data_limit
        return as_int(config.get(self.config_key)) if config else None

    @override
    async def async_set_native_value(self, value: float) -> None:
        config, _status = self.coordinator.active_data_limit
        if config is not None:
            await self.coordinator.async_update_data_limit(
                str(config["id"]), {self.config_key: str(round(value))}
            )


class TeltonikaCurrentDataLimitNumber(TeltonikaCurrentDataLimitConfigNumber):
    """Configure the active SIM data limit in MB."""

    _attr_translation_key = "current_data_limit_amount"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    config_key = "data_limit"

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "data_limit_amount")


class TeltonikaCurrentDataWarningNumber(TeltonikaCurrentDataLimitConfigNumber):
    """Configure the active SIM warning threshold in MB."""

    _attr_translation_key = "current_data_warning_threshold"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    config_key = "warning_limit"

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "data_warning_threshold")
