"""Teltonika SMS event platform."""

from __future__ import annotations

from typing import Any, ClassVar, override

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import modem_sim_identity, sms_message_fingerprint

PARALLEL_UPDATES = 0
SMS_RECEIVED = "received"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one received-SMS event entity per modem."""
    coordinator = entry.runtime_data
    known_modems: set[str] = set()

    @callback
    def _async_add_entities() -> None:
        new_modems = set(coordinator.data.modems) - known_modems
        if not coordinator.sms_supported or not new_modems:
            return
        async_add_entities(
            TeltonikaSmsEvent(coordinator, modem_id) for modem_id in new_modems
        )
        known_modems.update(new_modems)

    _async_add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_entities))


class TeltonikaSmsEvent(CoordinatorEntity[TeltonikaDataUpdateCoordinator], EventEntity):
    """Emit an event whenever the active SIM receives a new SMS."""

    _attr_has_entity_name = True
    _attr_translation_key = "sms_received"
    _attr_event_types: ClassVar[list[str]] = [SMS_RECEIVED]

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, modem_id: str
    ) -> None:
        """Initialize the received-SMS event entity."""
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{modem_id}_sms_received"
        modem = coordinator.data.modems[modem_id]
        self._attr_translation_placeholders = {
            "modem_name": modem.name or f"Modem {modem_id}"
        }
        self._sim_identity = modem_sim_identity(modem)
        self._known_messages = {
            sms_message_fingerprint(message) for message in self._messages_for_modem()
        }

    def _messages_for_modem(self) -> list[dict[str, Any]]:
        """Return SMS messages stored for this modem's active SIM."""
        return [
            message
            for message in self.coordinator.data.sms_messages
            if str(message.get("modem_id")) == self._modem_id
        ]

    @override
    def _handle_coordinator_update(self) -> None:
        """Trigger events for SMS messages first seen during this HA session."""
        modem = self.coordinator.data.modems.get(self._modem_id)
        if modem is None:
            super()._handle_coordinator_update()
            return

        messages = self._messages_for_modem()
        sim_identity = modem_sim_identity(modem)
        if sim_identity != self._sim_identity:
            # Messages are stored on the SIM. Seed the inbox after a SIM switch
            # so old messages on the newly selected card are not announced.
            self._sim_identity = sim_identity
            self._known_messages.update(
                sms_message_fingerprint(message) for message in messages
            )
            super()._handle_coordinator_update()
            return

        for message in sorted(messages, key=lambda item: str(item.get("date", ""))):
            fingerprint = sms_message_fingerprint(message)
            if fingerprint in self._known_messages:
                continue
            self._known_messages.add(fingerprint)
            event_data = {
                key: value
                for key, value in message.items()
                if key in {"id", "date", "sender", "status", "message", "modem_id"}
                and value is not None
            }
            self._trigger_event(SMS_RECEIVED, event_data)
            self.async_write_ha_state()

        super()._handle_coordinator_update()
