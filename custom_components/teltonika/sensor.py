"""Teltonika sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from teltasync.modems import ModemStatusFull

from . import TeltonikaConfigEntry
from .coordinator import TeltonikaDataUpdateCoordinator
from .helpers import as_float, as_int

PARALLEL_UPDATES = 0


def _ca_bands(modem: ModemStatusFull) -> str | None:
    """Return active carrier aggregation bands."""
    bands = [
        str(signal.band)
        for signal in (modem.ca_signal or [])
        if signal.band is not None
    ]
    if not bands:
        return modem.band
    return " + ".join(dict.fromkeys(bands))


@dataclass(frozen=True, kw_only=True)
class TeltonikaModemSensorDescription(SensorEntityDescription):
    """Describe a modem sensor."""

    value_fn: Callable[[ModemStatusFull], StateType]


MODEM_SENSORS: tuple[TeltonikaModemSensorDescription, ...] = (
    TeltonikaModemSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=0,
        value_fn=lambda modem: modem.rssi,
    ),
    TeltonikaModemSensorDescription(
        key="rsrp",
        translation_key="rsrp",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        suggested_display_precision=0,
        value_fn=lambda modem: modem.rsrp,
    ),
    TeltonikaModemSensorDescription(
        key="rsrq",
        translation_key="rsrq",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        suggested_display_precision=0,
        value_fn=lambda modem: modem.rsrq,
    ),
    TeltonikaModemSensorDescription(
        key="sinr",
        translation_key="sinr",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        suggested_display_precision=0,
        value_fn=lambda modem: modem.sinr,
    ),
    TeltonikaModemSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda modem: modem.temperature,
    ),
    TeltonikaModemSensorDescription(
        key="operator",
        translation_key="operator",
        value_fn=lambda modem: modem.operator,
    ),
    TeltonikaModemSensorDescription(
        key="connection_type",
        translation_key="connection_type",
        value_fn=lambda modem: modem.conntype,
    ),
    TeltonikaModemSensorDescription(
        key="band",
        translation_key="band",
        value_fn=lambda modem: modem.band,
    ),
    TeltonikaModemSensorDescription(
        key="ca_bands",
        translation_key="ca_bands",
        value_fn=_ca_bands,
    ),
    TeltonikaModemSensorDescription(
        key="active_sim",
        translation_key="active_sim",
        value_fn=lambda modem: modem.active_sim,
    ),
    TeltonikaModemSensorDescription(
        key="esim_profile",
        translation_key="esim_profile",
        value_fn=lambda modem: modem.esim_profile,
    ),
)


@dataclass(frozen=True, kw_only=True)
class TeltonikaGpsSensorDescription(SensorEntityDescription):
    """Describe a GPS sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]


GPS_SENSORS: tuple[TeltonikaGpsSensorDescription, ...] = (
    TeltonikaGpsSensorDescription(
        key="gps_latitude",
        translation_key="gps_latitude",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        suggested_display_precision=6,
        value_fn=lambda gps: as_float(gps.get("latitude")),
    ),
    TeltonikaGpsSensorDescription(
        key="gps_longitude",
        translation_key="gps_longitude",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        suggested_display_precision=6,
        value_fn=lambda gps: as_float(gps.get("longitude")),
    ),
    TeltonikaGpsSensorDescription(
        key="gps_altitude",
        translation_key="gps_altitude",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_display_precision=1,
        value_fn=lambda gps: as_float(gps.get("altitude")),
    ),
    TeltonikaGpsSensorDescription(
        key="gps_satellites",
        translation_key="gps_satellites",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda gps: as_int(gps.get("satellites")),
    ),
    TeltonikaGpsSensorDescription(
        key="gps_accuracy",
        translation_key="gps_accuracy",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda gps: as_float(gps.get("accuracy")),
    ),
    TeltonikaGpsSensorDescription(
        key="gps_speed",
        translation_key="gps_speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        value_fn=lambda gps: as_float(gps.get("speed")),
    ),
    TeltonikaGpsSensorDescription(
        key="gps_course",
        translation_key="gps_course",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        suggested_display_precision=1,
        value_fn=lambda gps: as_float(gps.get("angle")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeltonikaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Teltonika sensor platform."""
    coordinator = entry.runtime_data
    known_modems: set[str] = set()
    globals_added = False

    @callback
    def _async_add_entities() -> None:
        """Add newly discovered modem and optional global sensors."""
        nonlocal globals_added
        new_modems = set(coordinator.data.modems) - known_modems
        entities: list[SensorEntity] = [
            TeltonikaModemSensor(coordinator, description, modem_id)
            for modem_id in new_modems
            for description in MODEM_SENSORS
        ]
        if not globals_added:
            entities.extend(
                TeltonikaGpsSensor(coordinator, description)
                for description in GPS_SENSORS
            )
            entities.append(TeltonikaActiveWanSensor(coordinator))
            globals_added = True
        if entities:
            async_add_entities(entities)
            known_modems.update(new_modems)

    _async_add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_entities))


class TeltonikaBaseSensor(
    CoordinatorEntity[TeltonikaDataUpdateCoordinator], SensorEntity
):
    """Base class for Teltonika sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: TeltonikaDataUpdateCoordinator, unique_suffix: str
    ) -> None:
        """Initialize a sensor."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        assert coordinator.config_entry is not None
        entry_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"


class TeltonikaModemSensor(TeltonikaBaseSensor):
    """A sensor sourced from modem status."""

    entity_description: TeltonikaModemSensorDescription

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        description: TeltonikaModemSensorDescription,
        modem_id: str,
    ) -> None:
        """Initialize a modem sensor."""
        super().__init__(coordinator, f"{modem_id}_{description.key}")
        self.entity_description = description
        self._modem_id = modem_id
        modem = coordinator.data.modems[modem_id]
        self._attr_translation_key = description.translation_key
        self._attr_translation_placeholders = {
            "modem_name": modem.name or f"Modem {modem_id}"
        }

    @property
    @override
    def available(self) -> bool:
        """Return whether the modem is available."""
        return super().available and self._modem_id in self.coordinator.data.modems

    @property
    @override
    def native_value(self) -> StateType:
        """Return the current sensor value."""
        return self.entity_description.value_fn(
            self.coordinator.data.modems[self._modem_id]
        )

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose per-carrier details on the CA bands sensor."""
        if self.entity_description.key != "ca_bands":
            return None
        modem = self.coordinator.data.modems[self._modem_id]
        return {
            "carrier_aggregation": modem.sc_band_av,
            "carriers": [
                signal.model_dump(exclude_none=True)
                for signal in (modem.ca_signal or [])
            ],
        }


class TeltonikaGpsSensor(TeltonikaBaseSensor):
    """A GPS sensor."""

    entity_description: TeltonikaGpsSensorDescription

    def __init__(
        self,
        coordinator: TeltonikaDataUpdateCoordinator,
        description: TeltonikaGpsSensorDescription,
    ) -> None:
        """Initialize a GPS sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    @override
    def available(self) -> bool:
        """Return whether GPS data is available."""
        return super().available and self.coordinator.data.gps is not None

    @property
    @override
    def native_value(self) -> StateType:
        """Return the current GPS value."""
        return self.entity_description.value_fn(self.coordinator.data.gps or {})


class TeltonikaActiveWanSensor(TeltonikaBaseSensor):
    """Sensor showing the active Internet connection."""

    _attr_translation_key = "active_wan"

    def __init__(self, coordinator: TeltonikaDataUpdateCoordinator) -> None:
        """Initialize the active WAN sensor."""
        super().__init__(coordinator, "active_wan")

    @property
    @override
    def native_value(self) -> StateType:
        """Return the primary active WAN interface."""
        interfaces = self.coordinator.active_wan_interfaces()
        if not interfaces:
            return None
        interface = interfaces[0]
        return (
            interface.get("interface")
            or interface.get("id")
            or interface.get("ifname")
            or interface.get("name")
        )

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details for all active Internet connections."""
        interfaces = self.coordinator.active_wan_interfaces()
        primary = interfaces[0] if interfaces else {}
        return {
            "active_interfaces": [
                item.get("interface")
                or item.get("id")
                or item.get("ifname")
                or item.get("name")
                for item in interfaces
            ],
            "network_type": primary.get("network_type"),
            "device": primary.get("device") or primary.get("ifname"),
            "ip_addresses": primary.get("ipaddrs", []),
            "modem_id": primary.get("modem_id")
            or (
                primary.get("data", {}).get("modem")
                if isinstance(primary.get("data"), dict)
                else None
            ),
            "sim": primary.get("sim")
            or (
                primary.get("data", {}).get("sim")
                if isinstance(primary.get("data"), dict)
                else None
            ),
            "failover_status": primary.get("failover_status"),
        }
