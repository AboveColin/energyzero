"""Support for EnergyZero sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CURRENCY_EURO,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SERVICE_TYPE_DEVICE_NAMES
from .coordinator import EnergyZeroData, EnergyZeroDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class EnergyZeroSensorEntityDescription(SensorEntityDescription):
    """Describes an EnergyZero sensor entity."""

    value_fn: Callable[[HomeAssistant, EnergyZeroData], float | datetime | str | None]
    service_type: str


SENSORS: tuple[EnergyZeroSensorEntityDescription, ...] = (
    EnergyZeroSensorEntityDescription(
        key="current_hour_price",
        translation_key="current_hour_price",
        name="Current Hour Price",
        service_type="today_gas",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}",
        value_fn=lambda data: data.gas_today.current_price if data.gas_today else None,
    ),
    EnergyZeroSensorEntityDescription(
        key="next_hour_price",
        translation_key="next_hour_price",
        name="Next Hour Price",
        service_type="today_gas",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}",
        value_fn=lambda data: get_gas_price(data, 1),
    ),
    EnergyZeroSensorEntityDescription(
        key="current_hour_price",
        translation_key="current_hour_price",
        name="Current Hour Price",
        service_type="today_energy",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        value_fn=lambda data: data.energy_today.current_price,
    ),
    EnergyZeroSensorEntityDescription(
        key="next_hour_price",
        translation_key="next_hour_price",
        name="Next Hour Price",
        service_type="today_energy",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        value_fn=lambda data: data.energy_today.price_at_time(
            data.energy_today.utcnow() + timedelta(hours=1)
        ),
    ),
    EnergyZeroSensorEntityDescription(
        key="average_price",
        translation_key="average_price",
        name="Average Price Today",
        service_type="today_energy",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        value_fn=lambda data: data.energy_today.average_price,
    ),
    EnergyZeroSensorEntityDescription(
        key="max_price",
        translation_key="max_price",
        name="Highest Price Today",
        service_type="today_energy",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        value_fn=lambda data: data.energy_today.extreme_prices[1],
    ),
    EnergyZeroSensorEntityDescription(
        key="min_price",
        translation_key="min_price",
        name="Lowest Price Today",
        service_type="today_energy",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        value_fn=lambda data: data.energy_today.extreme_prices[0],
    ),
    EnergyZeroSensorEntityDescription(
        key="highest_price_time",
        translation_key="highest_price_time",
        name="Time of Highest Price Today",
        service_type="today_energy",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.energy_today.highest_price_time,
    ),
    EnergyZeroSensorEntityDescription(
        key="lowest_price_time",
        translation_key="lowest_price_time",
        name="Time of Lowest Price Today",
        service_type="today_energy",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.energy_today.lowest_price_time,
    ),
    EnergyZeroSensorEntityDescription(
        key="percentage_of_max",
        translation_key="percentage_of_max",
        name="Current Percentage of Highest Price",
        service_type="today_energy",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.energy_today.pct_of_max_price,
    ),
    EnergyZeroSensorEntityDescription(
        key="hours_priced_equal_or_lower",
        translation_key="hours_priced_equal_or_lower",
        name="Hours Priced Equal or Lower",
        service_type="today_energy",
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda data: data.energy_today.hours_priced_equal_or_lower,
    ),
    EnergyZeroSensorEntityDescription(
        key="timestamp_prices",
        translation_key="timestamp_prices",
        name="Hourly Prices Today",
        service_type="today_energy",
        value_fn=lambda hass, data: process_timestamp_prices(hass, data),
    ),
)

def process_timestamp_prices(hass: HomeAssistant, data: EnergyZeroData) -> str:
    """Process timestamp prices to a condensed string, adjusting for local timezone."""
    prices = data.energy_today.prices
    local_tz = dt_util.get_time_zone(hass.config.time_zone)
    
    # Convert UTC times to local timezone and sort
    local_prices = sorted(
        (dt_util.as_local(k.replace(tzinfo=dt_util.UTC)).replace(tzinfo=None), v)
        for k, v in prices.items()
    )
    
    # Create the string with sorted, timezone-adjusted prices
    return ",".join(f"{k.hour:02d}:{v:.2f}" for k, v in local_prices)


def get_gas_price(data: EnergyZeroData, hours: int) -> float | None:
    """Return the gas value.

    Args:
        data: The data object.
        hours: The number of hours to add to the current time.

    Returns:
        The gas market price value.

    """
    if data.gas_today is None:
        return None
    return data.gas_today.price_at_time(
        data.gas_today.utcnow() + timedelta(hours=hours)
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up EnergyZero Sensors based on a config entry."""
    coordinator: EnergyZeroDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EnergyZeroSensorEntity(
            coordinator=coordinator,
            description=description,
        )
        for description in SENSORS
    )


class EnergyZeroSensorEntity(
    CoordinatorEntity[EnergyZeroDataUpdateCoordinator], SensorEntity
):
    """Defines a EnergyZero sensor."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by EnergyZero"
    entity_description: EnergyZeroSensorEntityDescription

    def __init__(
        self,
        *,
        coordinator: EnergyZeroDataUpdateCoordinator,
        description: EnergyZeroSensorEntityDescription,
    ) -> None:
        """Initialize EnergyZero sensor."""
        super().__init__(coordinator=coordinator)
        self.entity_description = description
        self._attr_name = description.name
        self.entity_id = (
            f"{SENSOR_DOMAIN}.{DOMAIN}_{description.service_type}_{description.key}"
        )
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.service_type}_{description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={
                (
                    DOMAIN,
                    f"{coordinator.config_entry.entry_id}_{description.service_type}",
                )
            },
            manufacturer="EnergyZero",
            name=SERVICE_TYPE_DEVICE_NAMES[self.entity_description.service_type],
        )

@property
def native_value(self) -> float | datetime | str | None:
    """Return the state of the sensor."""
    if self.entity_description.key == "timestamp_prices":
        return self.entity_description.value_fn(self.hass, self.coordinator.data)
    return self.entity_description.value_fn(self.coordinator.data)
