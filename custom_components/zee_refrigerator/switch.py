"""Switch entities for the fridge's writable modes.

Each switch maps 1:1 to an attribute the fridge's own byte map publishes a single-
parameter write id for, so a toggle sends exactly one local EPP frame:

    Eco (energySavingStatus)         5D30
    Super Cool (quickRefrigeratingMode / 速冷)   5D24
    Super Freeze (quickFreezingMode / 速冻)      5D21
    Auto Set (intelligenceMode / 人工智慧)       5D20
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HaierFridgeCoordinator
from .decode import FridgeStatus


@dataclass(frozen=True, kw_only=True)
class FridgeSwitchDescription(SwitchEntityDescription):
    #: Key into ``const.WRITE_COMMANDS`` / the value sent by ``async_set_control``.
    control_key: str
    value_fn: Callable[[FridgeStatus], bool] = lambda s: False


SWITCH_TYPES: tuple[FridgeSwitchDescription, ...] = (
    FridgeSwitchDescription(
        key="eco",
        control_key="eco",
        translation_key="eco",
        value_fn=lambda s: s["eco"],
    ),
    FridgeSwitchDescription(
        key="super_cool",
        control_key="super_cool",
        translation_key="super_cool",
        icon="mdi:snowflake",
        value_fn=lambda s: s["super_cool"],
    ),
    FridgeSwitchDescription(
        key="super_freeze",
        control_key="super_freeze",
        translation_key="super_freeze",
        icon="mdi:snowflake-variant",
        value_fn=lambda s: s["super_freeze"],
    ),
    FridgeSwitchDescription(
        key="auto_set",
        control_key="auto_set",
        translation_key="auto_set",
        icon="mdi:auto-fix",
        value_fn=lambda s: s["auto_set"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HaierFridgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FridgeSwitch(coordinator, description) for description in SWITCH_TYPES
    )


class FridgeSwitch(CoordinatorEntity[HaierFridgeCoordinator], SwitchEntity):
    entity_description: FridgeSwitchDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HaierFridgeCoordinator,
        description: FridgeSwitchDescription,
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
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_control(self.entity_description.control_key, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_control(self.entity_description.control_key, False)
