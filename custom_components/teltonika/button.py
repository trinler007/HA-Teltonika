"""Teltonika action buttons."""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import sim_card_name, supports_sim_switch


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up physical SIM selection buttons."""
    coordinator = entry.runtime_data
    known_modems: set[str] = set()
    known_esim_modems: set[str] = set()

    @callback
    def _async_add_buttons() -> None:
        new_modems = {
            modem_id
            for modem_id, modem in coordinator.data.modems.items()
            if modem_id not in known_modems and supports_sim_switch(modem)
        }
        if new_modems:
            async_add_entities(
                TeltonikaSimButton(coordinator, modem_id, sim)
                for modem_id in new_modems
                for sim in (1, 2)
            )
            known_modems.update(new_modems)
        new_esim_modems = {
            modem_id
            for modem_id in coordinator.data.modems
            if modem_id not in known_esim_modems and coordinator.supports_esim(modem_id)
        }
        if new_esim_modems:
            async_add_entities(
                TeltonikaEsimButton(coordinator, modem_id)
                for modem_id in new_esim_modems
            )
            known_esim_modems.update(new_esim_modems)

    _async_add_buttons()
    async_add_entities(
        TeltonikaSmsLimitResetButton(coordinator, sim_card)
        for sim_card in coordinator.data.sim_cards
    )
    async_add_entities(
        [
            TeltonikaCurrentSmsLimitResetButton(coordinator),
            TeltonikaCurrentDataLimitResetButton(coordinator),
        ]
    )
    entry.async_on_unload(coordinator.async_add_listener(_async_add_buttons))


class TeltonikaSimButton(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], ButtonEntity
):
    """Select one physical SIM slot."""

    _attr_has_entity_name = True
    _attr_translation_key = "select_sim"

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        modem_id: str,
        sim: int,
    ) -> None:
        """Initialize a SIM selection button."""
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._sim = sim
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{modem_id}_select_sim_{sim}"
        modem = coordinator.data.modems[modem_id]
        self._attr_translation_placeholders = {
            "modem_name": modem.name or f"Modem {modem_id}",
            "sim_slot": str(sim),
        }

    @override
    async def async_press(self) -> None:
        """Select this SIM slot."""
        await self.coordinator.async_select_sim(self._modem_id, self._sim)


class TeltonikaEsimButton(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], ButtonEntity
):
    """Make the router eSIM active."""

    _attr_has_entity_name = True
    _attr_translation_key = "select_esim"

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        modem_id: str,
    ) -> None:
        """Initialize the eSIM activation button."""
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{modem_id}_select_esim"
        modem = coordinator.data.modems[modem_id]
        self._attr_translation_placeholders = {
            "modem_name": modem.name or f"Modem {modem_id}"
        }

    @override
    async def async_press(self) -> None:
        """Set the eSIM as default and make it active."""
        await self.coordinator.async_activate_esim(self._modem_id)


class TeltonikaSmsLimitResetButton(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], ButtonEntity
):
    """Clear the sent-SMS limit counter for one SIM configuration."""

    _attr_has_entity_name = True
    _attr_translation_key = "clear_sms_limit"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        sim_card: dict[str, object],
    ) -> None:
        super().__init__(coordinator)
        self._sim_card_id = str(sim_card["id"])
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{self._sim_card_id}_clear_sms_limit"
        self._attr_translation_placeholders = {"sim_name": sim_card_name(sim_card)}

    @override
    async def async_press(self) -> None:
        await self.coordinator.async_clear_sms_limit(self._sim_card_id)


class TeltonikaCurrentResetButton(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], ButtonEntity
):
    """Base class for an active-SIM reset action."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

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


class TeltonikaCurrentSmsLimitResetButton(TeltonikaCurrentResetButton):
    """Clear the SMS-limit counter of the active SIM."""

    _attr_translation_key = "current_clear_sms_limit"

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "clear_sms_limit")

    @property
    @override
    def available(self) -> bool:
        return super().available and self.coordinator.active_sim_card is not None

    @override
    async def async_press(self) -> None:
        config = self.coordinator.active_sim_card
        if config is not None:
            await self.coordinator.async_clear_sms_limit(str(config["id"]))


class TeltonikaCurrentDataLimitResetButton(TeltonikaCurrentResetButton):
    """Clear the data-limit counter of the active SIM."""

    _attr_translation_key = "current_clear_data_limit"

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "clear_data_limit")

    @property
    @override
    def available(self) -> bool:
        _config, status = self.coordinator.active_data_limit
        return super().available and status is not None

    @override
    async def async_press(self) -> None:
        _config, status = self.coordinator.active_data_limit
        if status is not None and status.get("interface"):
            await self.coordinator.async_clear_data_limit(str(status["interface"]))
