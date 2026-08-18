"""Finding a Haier fridge's LAN address without the cloud.

Used by the setup wizard's "Search the network for the fridge" option. The
mechanism mirrors the one enapt/haismart-local uses for AC units:

1. **ARP / DHCP** (``aiodiscover``, the same machinery Home Assistant's own ``dhcp``
   component uses). The fridge's deviceId *is* the Wi-Fi module's MAC, so an ARP scan
   identifies every host whose MAC starts with a Haier prefix; each candidate is then
   *asked* whether it is one of these appliances with a single unicast UDISCOVERY
   query. An answer to the query is the appliance identifying itself — a MAC-prefix
   match alone would also cover washing machines, so only queried devices are listed.
2. **A UDISCOVERY broadcast** as a backstop. Broadcast can be filtered or rate-limited
   by access points, so it is never relied upon alone.

Both paths are best-effort: this runs while someone is waiting on a form, so it never
raises — an empty list simply means the user types an address.
"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant

from .const import HAIER_OUIS
from .vendor.haismart_hrdp import DeviceInfo, async_query, discover

_LOGGER = logging.getLogger(__name__)

BROADCAST_TIMEOUT = 3.0


async def async_scan_for_appliances(
    hass: HomeAssistant, *, timeout: float = BROADCAST_TIMEOUT
) -> list[DeviceInfo]:
    """Every Haier appliance answering on this network, found without a key or an account."""
    candidates: list[str] = []
    try:
        from aiodiscover import DiscoverHosts

        for host in await DiscoverHosts().async_discover():
            mac = str(host.get("macaddress", "")).replace(":", "").upper()
            if mac.startswith(HAIER_OUIS) and host.get("ip"):
                candidates.append(str(host["ip"]))
    except Exception as err:  # noqa: BLE001 - best effort; aiodiscover ships with `dhcp`
        _LOGGER.debug("ARP scan unavailable: %s", err)

    found: list[DeviceInfo] = []
    if candidates:
        replies = await asyncio.gather(
            *(async_query(ip, timeout=timeout) for ip in candidates),
            return_exceptions=True,
        )
        found = [reply for reply in replies if isinstance(reply, DeviceInfo)]
    if found:
        return found

    try:
        return await hass.async_add_executor_job(lambda: discover(timeout=timeout))
    except OSError as err:
        _LOGGER.debug("broadcast discovery failed: %s", err)
        return []
