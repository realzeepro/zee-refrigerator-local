"""Sensor entities for the Zee Refrigerator integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HaierFridgeCoordinator
from .decode import FridgeStatus


@dataclass(frozen=True, kw_only=True)
class FridgeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[FridgeStatus], float | None] = lambda s: None


SENSOR_TYPES: tuple[FridgeSensorDescription, ...] = (
    FridgeSensorDescription(
        key="fridge_temp",
        translation_key="fridge_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda s: s["fridge_temp_c"],
    ),
    FridgeSensorDescription(
        key="freezer_temp",
        translation_key="freezer_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda s: s["freezer_temp_c"],
    ),
    FridgeSensorDescription(
        key="fridge_target_temp",
        translation_key="fridge_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=None,
        value_fn=lambda s: s["fridge_target_c"],
    ),
    FridgeSensorDescription(
        key="freezer_target_temp",
        translation_key="freezer_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda s: s["freezer_target_c"],
    ),
    FridgeSensorDescription(
        key="mode",
        translation_key="mode",
        device_class=SensorDeviceClass.ENUM,
        options=["Normal", "Eco", "Auto Set", "Super Freeze", "Super Cool"],
        value_fn=lambda s: s["mode"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HaierFridgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FridgeSensor(coordinator, description) for description in SENSOR_TYPES
    )


class FridgeSensor(CoordinatorEntity[HaierFridgeCoordinator], SensorEntity):
    entity_description: FridgeSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HaierFridgeCoordinator,
        description: FridgeSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer=MANUFACTURER,
            model=coordinator.model,
            name="Zee Refrigerator",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
