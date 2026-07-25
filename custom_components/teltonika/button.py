"""Teltonika action buttons."""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import supports_sim_switch


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
