"""Teltonika SIM and eSIM selectors."""

from __future__ import annotations

from typing import ClassVar, override

from homeassistant.components.select import SelectEntity
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
    """Set up SIM selectors."""
    coordinator = entry.runtime_data
    known_modems: set[str] = set()
    known_esim_modems: set[str] = set()

    @callback
    def _async_add_selectors() -> None:
        entities: list[SelectEntity] = []
        for modem_id, modem in coordinator.data.modems.items():
            if (
                supports_sim_switch(modem) or coordinator.supports_esim(modem_id)
            ) and modem_id not in known_modems:
                entities.append(TeltonikaSimSelect(coordinator, modem_id))
                known_modems.add(modem_id)

        esim_modems = {
            modem_id
            for modem_id in coordinator.data.modems
            if coordinator.esim_profiles_for_modem(modem_id)
        }
        for modem_id in esim_modems - known_esim_modems:
            entities.append(TeltonikaEsimSelect(coordinator, modem_id))
            known_esim_modems.add(modem_id)

        if entities:
            async_add_entities(entities)

    _async_add_selectors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_selectors))


class TeltonikaBaseSelect(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], SelectEntity
):
    """Base class for Teltonika selectors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        modem_id: str,
        unique_suffix: str,
    ) -> None:
        """Initialize a selector."""
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{modem_id}_{unique_suffix}"
        modem = coordinator.data.modems.get(modem_id)
        self._attr_translation_placeholders = {
            "modem_name": modem.name if modem and modem.name else f"Modem {modem_id}"
        }


class TeltonikaSimSelect(TeltonikaBaseSelect):
    """Select the active physical SIM."""

    _attr_translation_key = "active_sim"
    _physical_options: ClassVar[list[str]] = ["SIM 1", "SIM 2"]

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, modem_id: str
    ) -> None:
        """Initialize the SIM selector."""
        super().__init__(coordinator, modem_id, "active_sim_select")

    def _esim_profiles(self) -> list[dict[str, str]]:
        """Return selectable eSIM profiles for this modem."""
        return [
            profile
            for profile in self.coordinator.esim_profiles_for_modem(self._modem_id)
            if profile.get("profile_set", "1") == "1"
        ]

    @property
    @override
    def options(self) -> list[str]:
        """Return physical slots and installed eSIM profiles."""
        esim_source = ["eSIM"] if self.coordinator.supports_esim(self._modem_id) else []
        return (
            self._physical_options
            + esim_source
            + [
                f"eSIM: {profile.get('name') or profile['id']}"
                for profile in self._esim_profiles()
            ]
        )

    @property
    @override
    def current_option(self) -> str | None:
        """Return the active SIM."""
        modem = self.coordinator.data.modems.get(self._modem_id)
        if modem and modem.esim_profile:
            active = str(modem.esim_profile)
            profile = next(
                (
                    item
                    for item in self._esim_profiles()
                    if str(item.get("id")) == active or str(item.get("name")) == active
                ),
                None,
            )
            return (
                f"eSIM: {profile.get('name') or profile['id']}" if profile else "eSIM"
            )
        if self.coordinator.is_esim_active(self._modem_id):
            return "eSIM"
        return (
            f"SIM {modem.active_sim}" if modem and modem.active_sim in (1, 2) else None
        )

    @override
    async def async_select_option(self, option: str) -> None:
        """Select a SIM."""
        if option == "eSIM":
            await self.coordinator.async_activate_esim(self._modem_id)
            return
        if option.startswith("eSIM: "):
            selected = option.removeprefix("eSIM: ")
            profile = next(
                profile
                for profile in self._esim_profiles()
                if str(profile.get("name") or profile["id"]) == selected
            )
            await self.coordinator.async_select_esim_profile(str(profile["id"]))
            return
        await self.coordinator.async_select_sim(self._modem_id, int(option[-1]))


class TeltonikaEsimSelect(TeltonikaBaseSelect):
    """Select the active eSIM profile."""

    _attr_translation_key = "active_esim"

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, modem_id: str
    ) -> None:
        """Initialize the eSIM selector."""
        super().__init__(coordinator, modem_id, "active_esim_select")

    def _profiles(self) -> list[dict[str, str]]:
        return [
            profile
            for profile in self.coordinator.esim_profiles_for_modem(self._modem_id)
            if profile.get("profile_set", "1") == "1"
        ]

    @property
    @override
    def options(self) -> list[str]:
        """Return selectable profile names."""
        return [
            str(profile.get("name") or profile["id"]) for profile in self._profiles()
        ]

    @property
    @override
    def current_option(self) -> str | None:
        """Return the enabled eSIM profile."""
        profile = next(
            (profile for profile in self._profiles() if profile.get("enabled") == "1"),
            None,
        )
        return str(profile.get("name") or profile["id"]) if profile else None

    @override
    async def async_select_option(self, option: str) -> None:
        """Enable an eSIM profile."""
        profile = next(
            profile
            for profile in self._profiles()
            if str(profile.get("name") or profile["id"]) == option
        )
        await self.coordinator.async_select_esim_profile(str(profile["id"]))
