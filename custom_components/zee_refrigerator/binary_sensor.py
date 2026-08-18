"""Binary sensor entities for the Zee Refrigerator integration.

Modes (Eco / Auto Set / Super Cool / Super Freeze) are exposed as binary sensors,
not switches, because this integration is read-only: the fridge's firmware does
not accept local writes for this device family (see repo README). If you want to
toggle these from Home Assistant, do it via the Haismart app for now.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import HaierFridgeCoordinator
from .decode import FridgeStatus


@dataclass(frozen=True, kw_only=True)
class FridgeBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[FridgeStatus], bool | None] = lambda s: None


BINARY_SENSOR_TYPES: tuple[FridgeBinarySensorDescription, ...] = (
    FridgeBinarySensorDescription(
        key="fridge_door",
        translation_key="fridge_door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda s: s["fridge_door_open"],
    ),
    FridgeBinarySensorDescription(
        key="freezer_door",
        translation_key="freezer_door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda s: s["freezer_door_open"],
    ),
    FridgeBinarySensorDescription(
        key="eco_mode",
        translation_key="eco_mode",
        value_fn=lambda s: s["eco"],
    ),
    FridgeBinarySensorDescription(
        key="auto_set_mode",
        translation_key="auto_set_mode",
        value_fn=lambda s: s["auto_set"],
    ),
    FridgeBinarySensorDescription(
        key="super_freeze",
        translation_key="super_freeze",
        value_fn=lambda s: s["super_freeze"],
    ),
    FridgeBinarySensorDescription(
        key="super_cool",
        translation_key="super_cool",
        value_fn=lambda s: s["super_cool"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HaierFridgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FridgeBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_TYPES
    )


class FridgeBinarySensor(CoordinatorEntity[HaierFridgeCoordinator], BinarySensorEntity):
    entity_description: FridgeBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HaierFridgeCoordinator,
        description: FridgeBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="Zee Refrigerator",
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
