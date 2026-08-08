"""The Teltonika integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from teltasync import Teltasync

from .coordinator import TeltonikaDataUpdateCoordinator
from .util import normalize_url

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
    Platform.NOTIFY,
    Platform.SELECT,
    Platform.SENSOR,
]

TeltonikaConfigEntry = ConfigEntry[TeltonikaDataUpdateCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: TeltonikaConfigEntry) -> bool:
    """Migrate stored Teltonika entity preferences."""
    if entry.version > 1:
        return False

    if entry.version == 1 and entry.minor_version < 2:
        registry = er.async_get(hass)
        entry_prefix = entry.unique_id or entry.entry_id
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        ):
            unique_id = registry_entry.unique_id
            if not unique_id.startswith(f"{entry_prefix}_traffic_"):
                continue
            private_options = dict(registry_entry.options.get("sensor.private", {}))
            private_options["suggested_unit_of_measurement"] = (
                "MB"
                if "_traffic_today_" in unique_id or "_traffic_yesterday_" in unique_id
                else "GB"
            )
            registry.async_update_entity_options(
                registry_entry.entity_id,
                "sensor.private",
                private_options,
            )
        hass.config_entries.async_update_entry(entry, version=1, minor_version=2)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: TeltonikaConfigEntry) -> bool:
    """Set up Teltonika from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    validate_ssl = entry.data.get(CONF_VERIFY_SSL, False)
    session = async_get_clientsession(hass)

    base_url = normalize_url(host)

    client = Teltasync(
        base_url=f"{base_url}/api",
        username=username,
        password=password,
        session=session,
        verify_ssl=validate_ssl,
    )

    # Create coordinator
    coordinator = TeltonikaDataUpdateCoordinator(hass, client, entry, base_url)

    # Fetch initial data and set up device info
    await coordinator.async_config_entry_first_refresh()

    assert coordinator.device_info is not None

    try:
        await coordinator.async_start_nmea()
    except OSError as err:
        await client.close()
        raise ConfigEntryNotReady(
            f"Could not open the configured NMEA TCP port: {err}"
        ) from err

    # Store runtime data
    entry.runtime_data = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: TeltonikaConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop_nmea()
        await entry.runtime_data.client.close()

    return unload_ok
