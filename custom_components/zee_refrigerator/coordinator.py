"""DataUpdateCoordinator for the Zee Refrigerator local integration.

Handles local key rotation the same way enapt/haismart-local does for AC units:
if a Haier cloud account is configured (a durable refresh_token, not a password),
a rotated key is detected and silently re-fetched from the cloud MQTT gateway. If
no account is configured, or the refresh fails, a repair issue is raised asking
the user to re-key by hand via Settings > Devices > Zee Refrigerator > Configure.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from datetime import timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cloud_transport import async_cloud_transport
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLOUD_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_LOCALKEY_VERSION,
    CONF_LAYOUT,
    CONF_MODEL,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_STATUS_LEN,
    CONF_ZONE_INFO,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATUS_LEN,
    DEFAULT_TIMEOUT,
    DOMAIN,
    GATEWAY_TIMEOUT,
    MODEL,
    WRITE_TIMEOUT,
)
from .control import build_write_frame
from .decode import FridgeStatus, build_layout, decode, default_layout
from .vendor.haismart_extractor import GatewayCreds, GatewayError, HaierCloud, get_localkey_via_gateway
from .vendor.haismart_extractor.cloud import SEA_APP_CREDENTIALS, CloudError
from .vendor.haismart_hrdp import (
    LocalKeyRotated,
    async_read_status,
    async_send_op,
    reply_refused,
)

_LOGGER = logging.getLogger(__name__)

ISSUE_STALE_LOCALKEY = "stale_localkey"
ISSUE_KEY_REFRESH_FAILED = "key_refresh_failed"


class HaierFridgeCoordinator(DataUpdateCoordinator[FridgeStatus]):
    """Polls the fridge's local uSS/HRDP status report every scan interval.

    Reads the appliance on each poll and writes settings on demand
    (:meth:`async_set_control`), both over the same local protocol. The fridge accepts
    only one connection at a time, so reads and writes are serialised on a lock. It also
    writes a refreshed local key back to its own config entry when the fridge rotates its
    key and a cloud account is configured to auto-heal that.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.entry = entry
        self.host: str = entry.data["host"]
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self.local_key: str = entry.data[CONF_LOCAL_KEY]
        self.localkey_version: int | None = entry.data.get(CONF_LOCALKEY_VERSION)
        self.last_raw_status: str | None = None
        self.seen_lengths: list[int] = []
        # The fridge accepts ONE local connection at a time, so a poll and a control op
        # must never overlap — every session (read or write) is serialised on this lock.
        self._session = asyncio.Lock()

        options = entry.options
        self.status_len = int(options.get(CONF_STATUS_LEN, DEFAULT_STATUS_LEN))
        layout_json = options.get(CONF_LAYOUT)
        if layout_json:
            try:
                self.layout = build_layout(json.loads(layout_json))
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Ignoring invalid layout override in options; using the default layout"
                )
                self.layout = default_layout()
            else:
                self.status_len = self.layout["status_len"]
        else:
            self.layout = default_layout()
        self.model: str = options.get(CONF_MODEL) or MODEL

    async def _async_update_data(self) -> FridgeStatus:
        try:
            async with self._session:
                blobs = await async_read_status(
                    self.host,
                    self.device_id,
                    self.local_key,
                    timeout=DEFAULT_TIMEOUT,
                    expect_localkey_version=self.localkey_version,
                )
        except LocalKeyRotated as exc:
            if not await self._async_gateway_refresh():
                self._raise_stale_localkey_issue(self.localkey_version, exc.device_version)
                raise ConfigEntryAuthFailed(
                    "The fridge's local key has rotated and no cloud auto-refresh "
                    "succeeded. Add a Haier account under Settings > Devices > "
                    "Zee Refrigerator > Configure so future rotations heal "
                    "automatically, or re-fetch and paste in the current key by hand."
                ) from exc
            self.clear_stale_localkey_issue()
            # Retry once, now with the freshly refreshed key.
            try:
                async with self._session:
                    blobs = await async_read_status(
                        self.host,
                        self.device_id,
                        self.local_key,
                        timeout=DEFAULT_TIMEOUT,
                        expect_localkey_version=self.localkey_version,
                    )
            except (OSError, TimeoutError, RuntimeError) as retry_exc:
                raise UpdateFailed(
                    f"Key was refreshed but the retry still failed: {retry_exc}"
                ) from retry_exc
        except (OSError, TimeoutError, RuntimeError) as exc:
            raise UpdateFailed(f"Error communicating with fridge: {exc}") from exc

        self.seen_lengths = sorted({len(blob) for blob in blobs})
        self.last_raw_status = next(
            (blob.hex() for blob in blobs if len(blob) == self.status_len), None
        )
        status = next(
            (
                decode(blob, self.layout)
                for blob in blobs
                if len(blob) == self.status_len
            ),
            None,
        )
        if status is None:
            raise UpdateFailed(
                f"Fridge returned no decodable status (report lengths seen: "
                f"{self.seen_lengths}; expected {self.status_len} bytes). "
                f"This model's report layout may differ — set the byte map under "
                f"Options, or open an issue with the diagnostics download."
            )
        return status

    async def async_set_control(self, name: str, value: Any) -> None:
        """Send one local control write, then refresh the fridge's state.

        ``name`` is one of the keys in :data:`const.WRITE_COMMANDS`. Raises
        ``HomeAssistantError`` if the model publishes no write id for it, if the
        fridge refuses the command (frameType 0x03), or on a connection failure.
        Re-keys and retries once if the local key rotated, like the read path.
        """
        try:
            frame = build_write_frame(name, value)
        except ValueError as exc:
            raise HomeAssistantError(f"Cannot set {name}: {exc}") from exc

        blobs = await self._async_send_control_frame(name, frame)

        if reply_refused(blobs):
            raise HomeAssistantError(
                f"The fridge refused to change {name} (it may be locked out in its "
                f"current operating mode)."
            )

        # The op connection carries the fridge's routine status push FIRST (pre-change) and the
        # accepted answer (a fresh status report) after it, so decode NEWEST-first — taking the
        # first would show the pre-change state until the next poll.
        status = None
        for blob in reversed(blobs):
            if len(blob) != self.status_len:
                continue
            status = decode(blob, self.layout)
            if status is not None:
                self.last_raw_status = blob.hex()
                break
        if status is not None:
            self.async_set_updated_data(status)
        else:
            await self.async_request_refresh()

    async def _async_send_control_frame(self, name: str, frame: bytes) -> list[bytes]:
        """Run one control session, re-keying and retrying once on a key rotation."""
        try:
            async with self._session:
                return await async_send_op(
                    self.host,
                    self.device_id,
                    self.local_key,
                    frame,
                    counter=1,
                    timeout=WRITE_TIMEOUT,
                    expect_localkey_version=self.localkey_version,
                )
        except LocalKeyRotated as exc:
            if not await self._async_gateway_refresh():
                self._raise_stale_localkey_issue(self.localkey_version, exc.device_version)
                raise HomeAssistantError(
                    f"The fridge's local key rotated while setting {name}; no cloud "
                    f"auto-refresh succeeded — re-key under Configure."
                ) from exc
            self.clear_stale_localkey_issue()
            try:
                async with self._session:
                    return await async_send_op(
                        self.host,
                        self.device_id,
                        self.local_key,
                        frame,
                        counter=1,
                        timeout=WRITE_TIMEOUT,
                        expect_localkey_version=self.localkey_version,
                    )
            except (OSError, TimeoutError, RuntimeError) as again:
                raise HomeAssistantError(
                    f"Could not set {name} (after re-keying): {again}"
                ) from again
        except (OSError, TimeoutError, RuntimeError) as exc:
            raise HomeAssistantError(
                f"Could not reach the fridge to set {name}: {exc}"
            ) from exc

    async def _async_gateway_refresh(self) -> bool:
        """Fetch the current local key from the cloud MQTT gateway and update it in place.

        Returns True on success (key updated on self and persisted to the config entry,
        so the next read uses it); False if no account is configured or any step fails.
        """
        data = self.entry.data
        usdk_client_id = data.get(CONF_CLOUD_CLIENT_ID)
        refresh_token = data.get(CONF_REFRESH_TOKEN)
        if not usdk_client_id or not refresh_token:
            return False  # no cloud account configured for this entry

        access_token = data.get(CONF_ACCESS_TOKEN)
        try:
            cloud = HaierCloud(
                replace(SEA_APP_CREDENTIALS, client_id=usdk_client_id),
                access_token or "",
                zone_info=data.get(CONF_ZONE_INFO, "0"),
                transport=async_cloud_transport(self.hass),
            )
            access_token = (await cloud.refresh_token(refresh_token)).access_token
        except (CloudError, OSError, RuntimeError) as err:
            _LOGGER.warning("Cloud token refresh failed (%s)", err)
            if not access_token:
                return False  # nothing usable to try the gateway with

        creds = GatewayCreds.derive(usdk_client_id=usdk_client_id, access_token=access_token)
        try:
            local_key = await self.hass.async_add_executor_job(
                partial(get_localkey_via_gateway, creds, self.device_id, timeout=GATEWAY_TIMEOUT)
            )
        except (GatewayError, OSError, RuntimeError) as err:
            _LOGGER.warning("Gateway local key refresh failed for %s: %s", self.device_id, err)
            return False

        self.local_key = local_key.key
        self.localkey_version = local_key.version
        updates: dict[str, Any] = {
            CONF_LOCAL_KEY: local_key.key,
            CONF_LOCALKEY_VERSION: local_key.version,
        }
        if access_token and access_token != data.get(CONF_ACCESS_TOKEN):
            updates[CONF_ACCESS_TOKEN] = access_token
        self.hass.config_entries.async_update_entry(
            self.entry, data={**data, **updates}
        )
        _LOGGER.info("Local key auto-refreshed via the cloud gateway for %s", self.device_id)
        return True

    def _raise_stale_localkey_issue(self, old: int | None, current: Any) -> None:
        has_account = bool(self.entry.data.get(CONF_REFRESH_TOKEN))
        key = ISSUE_KEY_REFRESH_FAILED if has_account else ISSUE_STALE_LOCALKEY
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{key}_{self.device_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=key,
            translation_placeholders={
                "name": self.entry.title,
                "old": str(old),
                "new": str(current),
            },
        )

    def clear_stale_localkey_issue(self) -> None:
        for key in (ISSUE_STALE_LOCALKEY, ISSUE_KEY_REFRESH_FAILED):
            ir.async_delete_issue(self.hass, DOMAIN, f"{key}_{self.device_id}")
