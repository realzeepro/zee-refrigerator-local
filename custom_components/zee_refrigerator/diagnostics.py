"""Diagnostics for the Zee Refrigerator integration.

Includes the last raw 151-byte status hex, useful for extending the byte map if
you add sensors or need to reverse-engineer additional fields.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_TOKEN, CONF_LOCAL_KEY, CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import HaierFridgeCoordinator

TO_REDACT = {CONF_LOCAL_KEY, CONF_REFRESH_TOKEN, CONF_ACCESS_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: HaierFridgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": {k: v for k, v in entry.data.items() if k not in TO_REDACT},
        "options": dict(entry.options),
        "status_len": coordinator.status_len,
        "layout": coordinator.layout,
        "seen_report_lengths": coordinator.seen_lengths,
        "last_raw_status": coordinator.last_raw_status,
        "decoded_status": coordinator.data,
    }
