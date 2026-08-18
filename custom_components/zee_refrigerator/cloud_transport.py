"""HTTP transport for the cloud client, backed by Home Assistant's shared httpx client.

Building an ``httpx.AsyncClient`` from scratch loads the CA bundle from disk — a blocking
call inside the event loop that Home Assistant detects and warns about. HA already owns a
client whose SSL context was built off-loop at startup, so we reuse that instead.

Every call to the cloud (login, token refresh) should pass ``transport=async_cloud_transport(hass)``.
The local-key gateway fetch itself is unaffected — it runs in an executor.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback

from .vendor.haismart_extractor.cloud import Transport, httpx_transport

_LOGGER = logging.getLogger(__name__)


@callback
def async_cloud_transport(hass: HomeAssistant) -> Transport | None:
    """A Transport over HA's shared httpx client, or None to let the library use its own."""
    try:
        from homeassistant.helpers.httpx_client import get_async_client
    except ImportError:  # pragma: no cover - helper has existed for many releases
        _LOGGER.debug("HA httpx helper unavailable; using the library's own client")
        return None
    return httpx_transport(get_async_client(hass))
