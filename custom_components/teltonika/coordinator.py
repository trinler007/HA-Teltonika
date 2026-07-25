"""DataUpdateCoordinator for Teltonika."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING, Any, override

from aiohttp import ClientError
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
    CONF_POLL_INTERVAL,
    CONF_REVERSE_GEOCODING_ENABLED,
    CONF_REVERSE_GEOCODING_URL,
    DEFAULT_NMEA_PORT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_REVERSE_GEOCODING_URL,
    DOMAIN,
)
from .helpers import (
    active_wan_interfaces,
    as_float,
    as_int,
    data_usage_totals,
    distance_km,
    esim_profiles_for_modem,
    esim_sim_card_for_modem,
    is_enabled,
    is_esim_sim_card,
    modem_sim_switch_complete,
    reverse_geocode_location_name,
    supports_sim_switch,
)
from .nmea import NmeaTcpServer

if TYPE_CHECKING:
    from . import TeltonikaConfigEntry

_LOGGER = logging.getLogger(__name__)

NMEA_FALLBACK_TIMEOUT = 15
NMEA_STATUS_TIMEOUT = 30
TRAFFIC_REFRESH_INTERVAL = 300
GEOCODING_REFRESH_INTERVAL = 900
GEOCODING_MIN_DISTANCE_KM = 1.0
SIM_SWITCH_POLL_DELAYS = (2, 3, 5, 5, 5, 5, 5)
GEOCODING_USER_AGENT = (
    "HA-Teltonika/0.5.4 (+https://github.com/trinler007/HA-Teltonika)"
)


@dataclass(slots=True)
class TeltonikaData:
    """All data fetched during one coordinator update."""

    modems: dict[str, ModemStatusFull] = field(default_factory=dict)
    gps: dict[str, Any] | None = None
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    failover: dict[str, dict[str, Any]] = field(default_factory=dict)
    esim_profiles: list[dict[str, Any]] = field(default_factory=list)
    sim_cards: list[dict[str, Any]] = field(default_factory=list)
    system_usage: dict[str, Any] = field(default_factory=dict)
    traffic_usage: dict[str, dict[str, int]] = field(default_factory=dict)
    location_name: str | None = None
    location_details: dict[str, Any] = field(default_factory=dict)


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
            update_interval=timedelta(
                seconds=int(
                    config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
                )
            ),
            config_entry=config_entry,
        )
        self.client = client
        self.base_url = base_url
        self.firmware_version: str | None = None
        self.esim_supported = False
        self._nmea_server: NmeaTcpServer | None = None
        self._nmea_last_update: float | None = None
        self._nmea_last_received: datetime | None = None
        self._nmea_connected = False
        self._nmea_status_cancel: Callable[[], None] | None = None
        self._traffic_usage: dict[str, dict[str, int]] = {}
        self._traffic_ranges: dict[str, tuple[int, int]] = {}
        self._traffic_last_refresh: float | None = None
        self._location_name: str | None = None
        self._location_details: dict[str, Any] = {}
        self._geocoding_last_attempt: float | None = None
        self._geocoding_coordinates: tuple[float, float] | None = None

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

    @property
    def reverse_geocoding_enabled(self) -> bool:
        """Return whether optional reverse geocoding is enabled."""
        assert self.config_entry is not None
        return bool(
            self.config_entry.options.get(CONF_REVERSE_GEOCODING_ENABLED, False)
        )

    @callback
    def _async_publish_live_data(self, data: TeltonikaData) -> None:
        """Publish pushed data without delaying the scheduled API refresh."""
        self.data = data
        self.last_update_success = True
        self.async_update_listeners()

    def esim_profiles_for_modem(self, modem_id: str) -> list[dict[str, Any]]:
        """Return profiles assigned to a modem, including unambiguous legacy data."""
        return esim_profiles_for_modem(
            self.data.esim_profiles,
            list(self.data.modems),
            modem_id,
        )

    def supports_esim(self, modem_id: str) -> bool:
        """Return whether this router exposes an eSIM for a modem."""
        return self.esim_supported or any(
            str(sim_card.get("modem")) == modem_id and is_esim_sim_card(sim_card)
            for sim_card in self.data.sim_cards
        )

    def is_esim_active(self, modem_id: str) -> bool:
        """Return whether an eSIM is currently active on a modem."""
        modem = self.data.modems.get(modem_id)
        if modem is None:
            return False
        if modem.esim_profile:
            return True
        return any(
            str(sim_card.get("modem")) == modem_id
            and is_esim_sim_card(sim_card)
            and is_enabled(sim_card.get("primary"))
            and as_int(sim_card.get("position")) == modem.active_sim
            for sim_card in self.data.sim_cards
        )

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
        self._async_publish_live_data(replace(self.data, gps=gps))

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

    async def _async_update_location_name(self, gps: dict[str, Any] | None) -> None:
        """Resolve the current GPS coordinates to a worldwide place name."""
        if not self.reverse_geocoding_enabled or not gps:
            return
        latitude = as_float(gps.get("latitude"))
        longitude = as_float(gps.get("longitude"))
        if latitude is None or longitude is None or gps.get("fix_status") in (0, "0"):
            return

        if self._geocoding_last_attempt is not None:
            if monotonic() - self._geocoding_last_attempt < GEOCODING_REFRESH_INTERVAL:
                return
            if self._geocoding_coordinates is not None:
                moved = distance_km(
                    latitude,
                    longitude,
                    self._geocoding_coordinates[0],
                    self._geocoding_coordinates[1],
                )
                if moved is not None and moved < GEOCODING_MIN_DISTANCE_KM:
                    return

        self._geocoding_last_attempt = monotonic()
        self._geocoding_coordinates = (latitude, longitude)
        assert self.config_entry is not None
        endpoint = str(
            self.config_entry.options.get(
                CONF_REVERSE_GEOCODING_URL,
                DEFAULT_REVERSE_GEOCODING_URL,
            )
        )
        try:
            async with asyncio.timeout(10):
                async with self.client.auth.session.get(
                    endpoint,
                    params={
                        "format": "jsonv2",
                        "lat": latitude,
                        "lon": longitude,
                        "zoom": 10,
                        "addressdetails": 1,
                    },
                    headers={
                        "User-Agent": GEOCODING_USER_AGENT,
                        "Accept-Language": self.hass.config.language or "en",
                    },
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
        except (TimeoutError, ClientError, ValueError) as err:
            _LOGGER.debug("Reverse geocoding unavailable: %s", err)
            return

        address = payload.get("address")
        if not isinstance(address, dict):
            address = {}
        self._location_name = reverse_geocode_location_name(payload)
        self._location_details = {
            "display_name": payload.get("display_name"),
            "country_code": address.get("country_code"),
            "attribution": "© OpenStreetMap contributors",
            "provider": endpoint,
        }

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
        device_status = await self._async_optional_data("system/device/status")
        if isinstance(device_status, dict):
            board = device_status.get("board")
            hwinfo = board.get("hwinfo") if isinstance(board, dict) else None
            if isinstance(hwinfo, dict):
                self.esim_supported = is_enabled(hwinfo.get("esim"))

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
                sim_cards,
                system_usage,
                traffic_usage,
            ) = await asyncio.gather(
                self._async_optional_data("interfaces/status"),
                self._async_optional_data("failover/status"),
                self._async_optional_data("esim/config"),
                self._async_optional_data("sim_cards/config"),
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
        await self._async_update_location_name(gps)

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
            sim_cards=sim_cards if isinstance(sim_cards, list) else [],
            system_usage=system_usage if isinstance(system_usage, dict) else {},
            traffic_usage=traffic_usage,
            location_name=self._location_name,
            location_details=self._location_details,
        )

    async def async_select_sim(self, modem_id: str, sim: int) -> None:
        """Select a physical SIM on a dual-SIM modem."""
        modem = self.data.modems[modem_id]
        if modem.active_sim == sim and not modem.esim_profile:
            return
        if not supports_sim_switch(modem) or sim not in (1, 2):
            raise ValueError(
                "Direct SIM selection is only supported for dual-SIM modems"
            )

        sim_cards = await self._async_get_sim_cards()
        physical_sim = next(
            (
                sim_card
                for sim_card in sim_cards
                if str(sim_card.get("modem")) == modem_id
                and not is_esim_sim_card(sim_card)
                and as_int(sim_card.get("position")) == sim
            ),
            None,
        )
        if physical_sim is not None:
            await self._async_activate_sim_card(modem_id, physical_sim)
            await self._async_wait_for_sim_switch(
                modem_id,
                sim,
                expect_esim=False,
            )
            await self.async_request_refresh()
            return

        if modem.esim_profile:
            active = str(modem.esim_profile)
            profile = next(
                (
                    item
                    for item in self.esim_profiles_for_modem(modem_id)
                    if str(item.get("id")) == active or str(item.get("name")) == active
                ),
                None,
            )
            if profile is not None:
                await self._async_set_esim_profile(str(profile["id"]), enabled=False)
                await self.async_request_refresh()
                modem = self.data.modems[modem_id]
                if modem.active_sim == sim and not modem.esim_profile:
                    return

        await self.client.switch_sim(modem_id)
        await self._async_wait_for_sim_switch(
            modem_id,
            sim,
            expect_esim=False,
        )
        await self.async_request_refresh()

    async def async_activate_esim(self, modem_id: str) -> None:
        """Set the router eSIM as default, make it active, and rediscover profiles."""
        sim_cards = await self._async_get_sim_cards()
        modem = self.data.modems[modem_id]
        sim_card = esim_sim_card_for_modem(
            sim_cards,
            modem_id,
            str(modem.esim_profile) if modem.esim_profile else None,
        )
        if sim_card is None:
            raise TeltonikaConnectionError(
                "The router did not expose an eSIM entry in sim_cards/config"
            )

        await self._async_activate_sim_card(modem_id, sim_card)
        await self._async_wait_for_sim_switch(
            modem_id,
            as_int(sim_card.get("position")) or modem.active_sim,
            expect_esim=True,
        )
        for delay in (2, 3, 5):
            await asyncio.sleep(delay)
            profiles = await self._async_optional_data("esim/config")
            if isinstance(profiles, list) and profiles:
                self._async_publish_live_data(
                    replace(
                        self.data,
                        esim_profiles=profiles,
                        sim_cards=sim_cards,
                    )
                )
                break
        await self.async_request_refresh()

    async def async_select_esim_profile(self, profile_id: str) -> None:
        """Enable an eSIM profile."""
        await self._async_set_esim_profile(profile_id, enabled=True)
        await self.async_request_refresh()

    async def _async_set_esim_profile(self, profile_id: str, *, enabled: bool) -> None:
        """Enable or disable an eSIM profile."""
        response = await self.client.auth.request_json(
            "PUT",
            f"esim/config/{profile_id}",
            json={"data": {"enabled": "1" if enabled else "0"}},
        )
        if not response.get("success"):
            errors = response.get("errors") or []
            message = errors[0].get("error") if errors else "Unknown API error"
            action = "select" if enabled else "disable"
            raise TeltonikaConnectionError(
                f"Failed to {action} eSIM profile: {message}"
            )

    async def _async_get_sim_cards(self) -> list[dict[str, Any]]:
        """Fetch current SIM-card configuration."""
        sim_cards = await self._async_optional_data("sim_cards/config")
        if isinstance(sim_cards, list):
            return sim_cards
        return self.data.sim_cards

    async def _async_activate_sim_card(
        self, modem_id: str, sim_card: dict[str, Any]
    ) -> None:
        """Set a SIM-card configuration as default and restart the connection."""
        sim_card_id = sim_card.get("id")
        if not sim_card_id:
            raise TeltonikaConnectionError("SIM-card configuration has no ID")
        response = await self.client.auth.request_json(
            "PUT",
            f"sim_cards/config/{sim_card_id}",
            json={"data": {"primary": "1"}},
        )
        if not response.get("success"):
            raise TeltonikaConnectionError("Failed to set the default SIM")
        response = await self.client.auth.request_json(
            "POST",
            f"modems/{modem_id}/actions/restart_connection",
        )
        if not response.get("success"):
            raise TeltonikaConnectionError("Failed to make the default SIM active")

    async def _async_wait_for_sim_switch(
        self,
        modem_id: str,
        expected_sim: int,
        *,
        expect_esim: bool,
    ) -> None:
        """Poll modem status briefly until the selected SIM is initialized."""
        for delay in SIM_SWITCH_POLL_DELAYS:
            await asyncio.sleep(delay)
            try:
                response = await Modems(self.client.auth).get_status()
            except TeltonikaConnectionError as err:
                _LOGGER.debug(
                    "Modem status unavailable while waiting for SIM switch: %s",
                    err,
                )
                continue
            if not response.success:
                continue
            modems = {
                modem.id: modem
                for modem in (response.data or [])
                if isinstance(modem, ModemStatusFull)
            }
            if not modems:
                continue
            self._async_publish_live_data(replace(self.data, modems=modems))
            modem = modems.get(modem_id)
            if modem is not None and modem_sim_switch_complete(
                modem,
                expected_sim,
                expect_esim=expect_esim,
            ):
                return
        _LOGGER.debug(
            "SIM switch to %s on modem %s is still initializing; "
            "regular coordinator polling will continue",
            "eSIM" if expect_esim else f"SIM {expected_sim}",
            modem_id,
        )

    def active_wan_interfaces(self) -> list[dict[str, Any]]:
        """Return active Internet-facing interfaces in router priority order."""
        return active_wan_interfaces(self.data.interfaces, self.data.failover)
