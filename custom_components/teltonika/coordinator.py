"""DataUpdateCoordinator for Teltonika."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING, Any, override

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from teltasync import Teltasync, TeltonikaAuthenticationError, TeltonikaConnectionError
from teltasync.modems import Modems, ModemStatusFull

from .const import (
    CONF_NMEA_ENABLED,
    CONF_NMEA_PORT,
    DEFAULT_NMEA_PORT,
    DOMAIN,
)
from .helpers import active_wan_interfaces, data_usage_totals, supports_sim_switch
from .nmea import NmeaTcpServer

if TYPE_CHECKING:
    from . import TeltonikaConfigEntry

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
NMEA_FALLBACK_TIMEOUT = 15
NMEA_STATUS_TIMEOUT = 30
TRAFFIC_REFRESH_INTERVAL = 300


@dataclass(slots=True)
class TeltonikaData:
    """All data fetched during one coordinator update."""

    modems: dict[str, ModemStatusFull] = field(default_factory=dict)
    gps: dict[str, Any] | None = None
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    failover: dict[str, dict[str, Any]] = field(default_factory=dict)
    esim_profiles: list[dict[str, Any]] = field(default_factory=list)
    system_usage: dict[str, Any] = field(default_factory=dict)
    traffic_usage: dict[str, dict[str, int]] = field(default_factory=dict)


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
        self.firmware_version: str | None = None
        self._nmea_server: NmeaTcpServer | None = None
        self._nmea_last_update: float | None = None
        self._nmea_last_received: datetime | None = None
        self._nmea_connected = False
        self._nmea_status_cancel: Callable[[], None] | None = None
        self._traffic_usage: dict[str, dict[str, int]] = {}
        self._traffic_ranges: dict[str, tuple[int, int]] = {}
        self._traffic_last_refresh: float | None = None

    @property
    def nmea_enabled(self) -> bool:
        """Return whether the optional NMEA receiver is enabled."""
        assert self.config_entry is not None
        return bool(self.config_entry.options.get(CONF_NMEA_ENABLED, False))

    @property
    def nmea_active(self) -> bool:
        """Return whether fresh NMEA data is currently available."""
        return (
            self._nmea_last_update is not None
            and monotonic() - self._nmea_last_update < NMEA_FALLBACK_TIMEOUT
        )

    @property
    def nmea_status(self) -> bool:
        """Return whether NMEA is connected or recently delivered data."""
        return self.nmea_enabled and (
            self._nmea_connected
            or (
                self._nmea_last_update is not None
                and monotonic() - self._nmea_last_update <= NMEA_STATUS_TIMEOUT
            )
        )

    @property
    def nmea_connected(self) -> bool:
        """Return whether an NMEA TCP sender is connected."""
        return self._nmea_connected

    @property
    def nmea_last_received(self) -> datetime | None:
        """Return when the last valid NMEA sentence was received."""
        return self._nmea_last_received

    @property
    def nmea_port(self) -> int:
        """Return the configured NMEA TCP port."""
        assert self.config_entry is not None
        return int(self.config_entry.options.get(CONF_NMEA_PORT, DEFAULT_NMEA_PORT))

    async def async_start_nmea(self) -> None:
        """Start the optional TCP NMEA receiver."""
        if not self.nmea_enabled:
            return
        assert self.config_entry is not None
        self._nmea_server = NmeaTcpServer(
            self.nmea_port,
            self._async_process_nmea,
            self._async_process_nmea_connection,
        )
        await self._nmea_server.async_start()

    async def async_stop_nmea(self) -> None:
        """Stop the TCP NMEA receiver."""
        if self._nmea_server is not None:
            await self._nmea_server.async_stop()
            self._nmea_server = None
        if self._nmea_status_cancel is not None:
            self._nmea_status_cancel()
            self._nmea_status_cancel = None
        self._nmea_connected = False

    @callback
    def _async_process_nmea(self, update: dict[str, Any]) -> None:
        """Merge a live NMEA update into coordinator data."""
        gps = dict(self.data.gps or {})
        gps.update(update)
        received_at = dt_util.utcnow()
        gps["source"] = "nmea"
        gps["received_at"] = received_at.isoformat()
        self._nmea_last_update = monotonic()
        self._nmea_last_received = received_at
        if self._nmea_status_cancel is not None:
            self._nmea_status_cancel()
        self._nmea_status_cancel = async_call_later(
            self.hass,
            NMEA_STATUS_TIMEOUT,
            self._async_nmea_status_expired,
        )
        self.async_set_updated_data(replace(self.data, gps=gps))

    @callback
    def _async_process_nmea_connection(self, connected: bool) -> None:
        """Handle a change to the NMEA TCP connection state."""
        self._nmea_connected = connected
        self.async_update_listeners()

    @callback
    def _async_nmea_status_expired(self, _now: datetime) -> None:
        """Notify entities when the recent-data status expires."""
        self._nmea_status_cancel = None
        self.async_update_listeners()

    @staticmethod
    def _traffic_periods(now: datetime) -> dict[str, tuple[int, int]]:
        """Return calendar-aligned traffic periods as Unix timestamps."""
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        month = today.replace(day=1)
        previous_month_end = month - timedelta(seconds=1)
        previous_month = previous_month_end.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return {
            "today": (int(today.timestamp()), int(now.timestamp())),
            "yesterday": (
                int(yesterday.timestamp()),
                int(today.timestamp()) - 1,
            ),
            "current_month": (int(month.timestamp()), int(now.timestamp())),
            "previous_month": (
                int(previous_month.timestamp()),
                int(previous_month_end.timestamp()),
            ),
        }

    async def _async_update_traffic_usage(self) -> dict[str, dict[str, int]]:
        """Refresh current traffic counters and cache closed periods."""
        if (
            self._traffic_last_refresh is not None
            and monotonic() - self._traffic_last_refresh < TRAFFIC_REFRESH_INTERVAL
        ):
            return self._traffic_usage

        periods = self._traffic_periods(dt_util.now())
        current_periods = {"today", "current_month"}
        requested = {
            name: value
            for name, value in periods.items()
            if name in current_periods or self._traffic_ranges.get(name) != value
        }
        results = await asyncio.gather(
            *(
                self._async_optional_data(
                    "data_usage/custom/status",
                    params={"from": start, "to": end},
                )
                for start, end in requested.values()
            )
        )
        for (name, period), entries in zip(requested.items(), results, strict=True):
            if isinstance(entries, list):
                self._traffic_usage[name] = data_usage_totals(entries)
                self._traffic_ranges[name] = period
        self._traffic_last_refresh = monotonic()
        return self._traffic_usage

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
        self.firmware_version = system_info_response.static.fw_version

    async def _async_optional_data(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Return data from an optional endpoint, or None when unsupported."""
        try:
            response = await self.client.auth.request_json(
                "GET", endpoint, params=params
            )
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

            use_nmea = self.nmea_active
            gps_from_api = None
            (
                interfaces,
                failover,
                esim_profiles,
                system_usage,
                traffic_usage,
            ) = await asyncio.gather(
                self._async_optional_data("interfaces/status"),
                self._async_optional_data("failover/status"),
                self._async_optional_data("esim/config"),
                self._async_optional_data("system/device/usage/status"),
                self._async_update_traffic_usage(),
            )
            if not use_nmea:
                gps_from_api = await self._async_optional_data("gps/position/status")
        except TeltonikaAuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except TeltonikaConnectionError as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err

        if self.nmea_active or use_nmea:
            gps = self.data.gps
        elif isinstance(gps_from_api, dict):
            gps = {**gps_from_api, "source": "api"}
        else:
            gps = None

        return TeltonikaData(
            modems={
                modem.id: modem
                for modem in (modems_response.data or [])
                if isinstance(modem, ModemStatusFull)
            },
            gps=gps,
            interfaces=interfaces if isinstance(interfaces, list) else [],
            failover=failover if isinstance(failover, dict) else {},
            esim_profiles=esim_profiles if isinstance(esim_profiles, list) else [],
            system_usage=system_usage if isinstance(system_usage, dict) else {},
            traffic_usage=traffic_usage,
        )

    async def async_select_sim(self, modem_id: str, sim: int) -> None:
        """Select a physical SIM on a dual-SIM modem."""
        modem = self.data.modems[modem_id]
        if modem.active_sim == sim:
            return
        if not supports_sim_switch(modem) or sim not in (1, 2):
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
