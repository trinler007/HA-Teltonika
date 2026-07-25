"""DataUpdateCoordinator for Teltonika."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any, override

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from teltasync import Teltasync, TeltonikaAuthenticationError, TeltonikaConnectionError
from teltasync.modems import Modems, ModemStatusFull

from .const import DOMAIN
from .helpers import active_wan_interfaces

if TYPE_CHECKING:
    from . import TeltonikaConfigEntry

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


@dataclass(slots=True)
class TeltonikaData:
    """All data fetched during one coordinator update."""

    modems: dict[str, ModemStatusFull] = field(default_factory=dict)
    gps: dict[str, Any] | None = None
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    failover: dict[str, dict[str, Any]] = field(default_factory=dict)
    esim_profiles: list[dict[str, Any]] = field(default_factory=list)


class TeltonikaDataUpdateCoordinator(DataUpdateCoordinator[TeltonikaData]):
    """Class to manage fetching Teltonika data."""

    device_info: DeviceInfo

    def __init__(
        self,
        hass: HomeAssistant,
        client: Teltasync,
        config_entry: TeltonikaConfigEntry,
        base_url: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Teltonika",
            update_interval=SCAN_INTERVAL,
            config_entry=config_entry,
        )
        self.client = client
        self.base_url = base_url

    @override
    async def _async_setup(self) -> None:
        """Authenticate and fetch device information."""
        try:
            await self.client.get_device_info()
            system_info_response = await self.client.get_system_info()
        except TeltonikaAuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except TeltonikaConnectionError as err:
            raise ConfigEntryNotReady(f"Failed to connect to device: {err}") from err

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, system_info_response.mnf_info.serial)},
            connections={
                (CONNECTION_NETWORK_MAC, mac)
                for mac in (
                    system_info_response.mnf_info.mac_eth,
                    system_info_response.mnf_info.mac,
                )
                if mac
            },
            name=system_info_response.static.device_name,
            manufacturer="Teltonika",
            model=system_info_response.static.model,
            sw_version=system_info_response.static.fw_version,
            serial_number=system_info_response.mnf_info.serial,
            configuration_url=self.base_url,
        )

    async def _async_optional_data(self, endpoint: str) -> Any:
        """Return data from an optional endpoint, or None when unsupported."""
        try:
            response = await self.client.auth.request_json("GET", endpoint)
        except TeltonikaAuthenticationError:
            raise
        except TeltonikaConnectionError as err:
            _LOGGER.debug("Optional endpoint %s unavailable: %s", endpoint, err)
            return None

        if not response.get("success"):
            _LOGGER.debug(
                "Optional endpoint %s returned an error: %s",
                endpoint,
                response.get("errors"),
            )
            return None
        return response.get("data")

    @override
    async def _async_update_data(self) -> TeltonikaData:
        """Fetch data from the Teltonika device."""
        try:
            modems_response = await Modems(self.client.auth).get_status()
            if not modems_response.success:
                error_message = (
                    modems_response.errors[0].error
                    if modems_response.errors
                    else "Unknown API error"
                )
                raise UpdateFailed(error_message)

            gps, interfaces, failover, esim_profiles = await asyncio.gather(
                self._async_optional_data("gps/position/status"),
                self._async_optional_data("interfaces/status"),
                self._async_optional_data("failover/status"),
                self._async_optional_data("esim/config"),
            )
        except TeltonikaAuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except TeltonikaConnectionError as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err

        return TeltonikaData(
            modems={
                modem.id: modem
                for modem in (modems_response.data or [])
                if isinstance(modem, ModemStatusFull)
            },
            gps=gps if isinstance(gps, dict) else None,
            interfaces=interfaces if isinstance(interfaces, list) else [],
            failover=failover if isinstance(failover, dict) else {},
            esim_profiles=esim_profiles if isinstance(esim_profiles, list) else [],
        )

    async def async_select_sim(self, modem_id: str, sim: int) -> None:
        """Select a physical SIM on a dual-SIM modem."""
        modem = self.data.modems[modem_id]
        if modem.active_sim == sim:
            return
        if modem.sim_count != 2 or sim not in (1, 2):
            raise ValueError(
                "Direct SIM selection is only supported for dual-SIM modems"
            )
        await self.client.switch_sim(modem_id)
        await self.async_request_refresh()

    async def async_select_esim_profile(self, profile_id: str) -> None:
        """Enable an eSIM profile."""
        response = await self.client.auth.request_json(
            "PUT",
            f"esim/config/{profile_id}",
            json={"data": {"enabled": "1"}},
        )
        if not response.get("success"):
            errors = response.get("errors") or []
            message = errors[0].get("error") if errors else "Unknown API error"
            raise TeltonikaConnectionError(f"Failed to select eSIM profile: {message}")
        await self.async_request_refresh()

    def active_wan_interfaces(self) -> list[dict[str, Any]]:
        """Return active Internet-facing interfaces in router priority order."""
        return active_wan_interfaces(self.data.interfaces, self.data.failover)
