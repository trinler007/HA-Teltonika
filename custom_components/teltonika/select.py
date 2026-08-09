"""Teltonika SIM and eSIM selectors."""

from __future__ import annotations

from typing import Any, ClassVar, override

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import is_esim_profile_active, sim_card_name, supports_sim_switch


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SIM selectors."""
    coordinator = entry.runtime_data
    known_modems: set[str] = set()
    known_esim_modems: set[str] = set()

    async_add_entities(
        TeltonikaSmsLimitPeriodSelect(coordinator, sim_card)
        for sim_card in coordinator.data.sim_cards
    )
    async_add_entities(
        [
            TeltonikaCurrentSmsLimitPeriodSelect(coordinator),
            TeltonikaCurrentDataLimitPeriodSelect(coordinator),
            TeltonikaCurrentDataLimitResetSelect(coordinator),
        ]
    )

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
        return self.coordinator.esim_profiles_for_modem(self._modem_id)

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
                    if is_esim_profile_active(item)
                    or str(item.get("id")) == active
                    or str(item.get("name")) == active
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
        """Return all installed eSIM profiles for this modem."""
        return self.coordinator.esim_profiles_for_modem(self._modem_id)

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
            (
                profile
                for profile in self._profiles()
                if is_esim_profile_active(profile)
            ),
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


class TeltonikaSmsLimitPeriodSelect(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], SelectEntity
):
    """Configure the SMS limit reset period for one SIM."""

    _attr_has_entity_name = True
    _attr_translation_key = "sms_limit_period"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = ["day", "week", "month"]

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, sim_card: dict[str, str]
    ) -> None:
        super().__init__(coordinator)
        self._sim_card_id = str(sim_card["id"])
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{self._sim_card_id}_sms_limit_period"
        self._attr_translation_placeholders = {"sim_name": sim_card_name(sim_card)}

    @property
    @override
    def current_option(self) -> str | None:
        config = next(
            (
                item
                for item in self.coordinator.data.sim_cards
                if str(item.get("id")) == self._sim_card_id
            ),
            None,
        )
        value = str(config.get("sms_limit")) if config else None
        return value if value in self.options else None

    @override
    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_update_sim_card(
            self._sim_card_id, {"sms_limit": option}
        )


class TeltonikaCurrentSelect(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], SelectEntity
):
    """Base class for an active-SIM select entity."""

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


class TeltonikaCurrentSmsLimitPeriodSelect(TeltonikaCurrentSelect):
    """Configure the active SIM SMS-limit period."""

    _attr_translation_key = "current_sms_limit_period"
    _attr_options = ["day", "week", "month"]

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "sms_limit_period")

    @property
    @override
    def available(self) -> bool:
        return super().available and self.coordinator.active_sim_card is not None

    @property
    @override
    def current_option(self) -> str | None:
        config = self.coordinator.active_sim_card or {}
        value = str(config.get("sms_limit") or "")
        return value if value in self.options else None

    @override
    async def async_select_option(self, option: str) -> None:
        config = self.coordinator.active_sim_card
        if config is not None:
            await self.coordinator.async_update_sim_card(
                str(config["id"]), {"sms_limit": option}
            )


class TeltonikaCurrentDataLimitPeriodSelect(TeltonikaCurrentSelect):
    """Configure the active SIM data-limit reset period."""

    _attr_translation_key = "current_data_limit_period"
    _attr_options = ["day", "week", "month"]

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "data_limit_period")

    @property
    @override
    def available(self) -> bool:
        config, _status = self.coordinator.active_data_limit
        return super().available and config is not None

    @property
    @override
    def current_option(self) -> str | None:
        config, _status = self.coordinator.active_data_limit
        value = str(config.get("period") or "") if config else ""
        return value if value in self.options else None

    @override
    async def async_select_option(self, option: str) -> None:
        config, _status = self.coordinator.active_data_limit
        if config is None:
            return
        schedule_key = {
            "day": "reset_hour",
            "week": "reset_weekday",
            "month": "reset_day",
        }[option]
        await self.coordinator.async_update_data_limit(
            str(config["id"]),
            {
                "period": option,
                schedule_key: str(
                    config.get(schedule_key) or ("0" if option == "day" else "1")
                ),
            },
        )


class TeltonikaCurrentDataLimitResetSelect(TeltonikaCurrentSelect):
    """Configure the period-dependent active SIM reset point."""

    _attr_translation_key = "current_data_limit_reset"
    _weekdays: ClassVar[list[str]] = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "data_limit_reset")

    @property
    def _config(self) -> dict[str, Any] | None:
        config, _status = self.coordinator.active_data_limit
        return config

    @property
    @override
    def available(self) -> bool:
        return super().available and self._config is not None

    @property
    @override
    def options(self) -> list[str]:
        period = str((self._config or {}).get("period") or "month")
        if period == "day":
            return [f"{hour:02}:00" for hour in range(24)]
        if period == "week":
            return self._weekdays
        return [str(day) for day in range(1, 32)]

    @property
    @override
    def current_option(self) -> str | None:
        config = self._config or {}
        period = str(config.get("period") or "month")
        if period == "day":
            hour = int(config.get("reset_hour") or 0)
            return f"{hour:02}:00"
        if period == "week":
            weekday = int(config.get("reset_weekday") or 1)
            return self._weekdays[weekday - 1] if 1 <= weekday <= 7 else None
        value = str(config.get("reset_day") or "1")
        return value if value in self.options else None

    @override
    async def async_select_option(self, option: str) -> None:
        config = self._config
        if config is None:
            return
        period = str(config.get("period") or "month")
        if period == "day":
            values = {"reset_hour": str(int(option.split(":", maxsplit=1)[0]))}
        elif period == "week":
            values = {"reset_weekday": str(self._weekdays.index(option) + 1)}
        else:
            values = {"reset_day": option}
        await self.coordinator.async_update_data_limit(str(config["id"]), values)
