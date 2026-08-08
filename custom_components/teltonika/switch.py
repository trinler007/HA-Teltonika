"""Teltonika modem and SIM configuration switches."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import is_enabled, sim_card_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up modem and per-SIM switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            TeltonikaFlightModeSwitch(coordinator, modem_id)
            for modem_id in coordinator.data.modem_configs
        ]
        + [
            entity
            for sim_card in coordinator.data.sim_cards
            for entity in (
                TeltonikaDataRoamingSwitch(coordinator, sim_card),
                TeltonikaSmsLimitSwitch(coordinator, sim_card),
            )
        ]
    )


class TeltonikaSimConfigSwitch(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], SwitchEntity
):
    """Base class for switches stored in one SIM configuration section."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    config_key: str

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        sim_card: dict[str, Any],
        suffix: str,
    ) -> None:
        """Initialize a SIM configuration switch."""
        super().__init__(coordinator)
        self._sim_card_id = str(sim_card["id"])
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{self._sim_card_id}_{suffix}"
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
    def available(self) -> bool:
        return super().available and self._config is not None

    async def _async_set(self, enabled: bool) -> None:
        await self.coordinator.async_update_sim_card(
            self._sim_card_id, {self.config_key: "1" if enabled else "0"}
        )

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)


class TeltonikaDataRoamingSwitch(TeltonikaSimConfigSwitch):
    """Allow or deny data roaming for one SIM configuration."""

    _attr_translation_key = "data_roaming"
    config_key = "deny_roaming"

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, sim_card: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, sim_card, "data_roaming")

    @property
    @override
    def is_on(self) -> bool:
        config = self._config
        return bool(config) and not is_enabled(config.get(self.config_key))

    async def _async_set(self, enabled: bool) -> None:
        await self.coordinator.async_update_sim_card(
            self._sim_card_id, {self.config_key: "0" if enabled else "1"}
        )


class TeltonikaSmsLimitSwitch(TeltonikaSimConfigSwitch):
    """Enable the sent-SMS limit for one SIM configuration."""

    _attr_translation_key = "sms_limit"
    config_key = "enable_sms_limit"

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, sim_card: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, sim_card, "sms_limit")

    @property
    @override
    def is_on(self) -> bool:
        config = self._config
        return bool(config) and is_enabled(config.get(self.config_key))


class TeltonikaFlightModeSwitch(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], SwitchEntity
):
    """Control flight mode for one modem."""

    _attr_has_entity_name = True
    _attr_translation_key = "flight_mode"
    _attr_entity_category = EntityCategory.CONFIG

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
        self._attr_unique_id = f"{entry_id}_{modem_id}_flight_mode"
        modem = coordinator.data.modems.get(modem_id)
        self._attr_translation_placeholders = {
            "modem_name": modem.name if modem and modem.name else f"Modem {modem_id}"
        }

    @property
    @override
    def available(self) -> bool:
        return (
            super().available
            and self._modem_id in self.coordinator.data.modem_configs
        )

    @property
    @override
    def is_on(self) -> bool:
        config = self.coordinator.data.modem_configs.get(self._modem_id, {})
        return is_enabled(config.get("flight_mode"))

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_flight_mode(self._modem_id, True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_flight_mode(self._modem_id, False)
