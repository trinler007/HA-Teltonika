"""Teltonika SMS notification platform."""

from __future__ import annotations

from typing import override

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from teltasync import TeltonikaConnectionError

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one SMS notifier per modem."""
    coordinator = entry.runtime_data
    known_modems: set[str] = set()

    @callback
    def _async_add_entities() -> None:
        new_modems = set(coordinator.data.modems) - known_modems
        if not coordinator.sms_supported or not new_modems:
            return
        async_add_entities(
            TeltonikaSmsNotify(coordinator, modem_id) for modem_id in new_modems
        )
        known_modems.update(new_modems)

    _async_add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_entities))


class TeltonikaSmsNotify(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], NotifyEntity
):
    """Send SMS messages using the currently active SIM."""

    _attr_has_entity_name = True
    _attr_translation_key = "sms"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, modem_id: str
    ) -> None:
        """Initialize the SMS notifier."""
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{modem_id}_sms_notify"
        modem = coordinator.data.modems[modem_id]
        self._attr_translation_placeholders = {
            "modem_name": modem.name or f"Modem {modem_id}"
        }

    @override
    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send an SMS; Home Assistant's title field contains the recipient."""
        phone_number = title.strip() if title else ""
        if not phone_number:
            raise ServiceValidationError(
                "The title field must contain the recipient phone number"
            )
        if not message.strip():
            raise ServiceValidationError("The SMS message must not be empty")
        try:
            await self.coordinator.async_send_sms(self._modem_id, phone_number, message)
        except TeltonikaConnectionError as err:
            raise HomeAssistantError(f"Could not send SMS: {err}") from err
