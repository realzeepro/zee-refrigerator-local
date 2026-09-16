"""Number entity: the fridge's target temperature level.

The fridge is controlled by a *level* (2..10, where 2 = 1 °C and 10 = 9 °C), which is
what Haier's own app exposes and what the local write id (``5D02``) sets. The level is
kept as-is rather than converted to °C so the value on the wire matches the value shown.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, TARGET_LEVEL_MAX, TARGET_LEVEL_MIN
from .coordinator import HaierFridgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HaierFridgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FridgeTargetLevel(coordinator)])


class FridgeTargetLevel(CoordinatorEntity[HaierFridgeCoordinator], NumberEntity):
    """The fridge's target level (2..10)."""

    _attr_has_entity_name = True
    _attr_translation_key = "target_level"
    _attr_native_min_value = TARGET_LEVEL_MIN
    _attr_native_max_value = TARGET_LEVEL_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: HaierFridgeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_target_level"
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
        return self.coordinator.data.get("target_level")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_control("target_level", int(value))
