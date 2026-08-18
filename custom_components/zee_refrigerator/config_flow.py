"""Config flow for the Zee Refrigerator (local, monitoring-only) integration.

Two ways to set up:
  * Manual — paste the current local key. Works immediately, but you'll need to
    re-paste a new key by hand whenever the fridge rotates it.
  * Haier account (optional) — sign in once (email/phone + password). The key is
    fetched automatically, and future rotations are re-fetched automatically too.
    Only a durable refresh_token is stored, never the password.
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .cloud_transport import async_cloud_transport
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLOUD_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_LOCALKEY_VERSION,
    CONF_REFRESH_TOKEN,
    CONF_ZONE_INFO,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    GATEWAY_TIMEOUT,
)
from .countries import COUNTRY_DIAL_CODES, default_dial_code
from .vendor.haismart_extractor import GatewayCreds, GatewayError, HaierCloud, get_localkey_via_gateway
from .vendor.haismart_extractor.cloud import SEA_APP_CREDENTIALS, CloudError
from .vendor.haismart_hrdp import async_query, async_read_status

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("setup_method", default="manual"): vol.In(
            {"manual": "Enter local key manually", "account": "Sign in with Haier account"}
        ),
    }
)

STEP_MANUAL_KEY_SCHEMA = vol.Schema({vol.Required(CONF_LOCAL_KEY): str})


def _country_select() -> vol.In:
    """The account region as a dropdown (``Country (+code)``).

    The value sent to Haier is the bare dialling code (``91``, ``66``); the label shows the country
    alongside it. ``vol.In`` over a mapping renders a select in the frontend on every HA version,
    unlike ``vol.Select`` which needs a recent patch on the ``vol`` namespace.
    """
    return vol.In(
        {code: f"{name} (+{code})" for name, code in sorted(COUNTRY_DIAL_CODES.values())}
    )


def _account_schema(default_zone: str | None) -> vol.Schema:
    """The account step, with the region the account was registered in.

    The region is the phone dialling code Haier's API wants as ``zoneInfo``; it routes the account
    lookup, so a wrong value comes back as "account not registered" even with correct credentials.
    """
    return vol.Schema(
        {
            vol.Required("login_id"): str,
            vol.Required("password"): str,
            vol.Required(CONF_ZONE_INFO, default=default_zone): _country_select(),
        }
    )


class HaierFridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._device_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input["host"]
            info = await async_query(self._host)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                self._device_id = info.device_id
                await self.async_set_unique_id(info.device_id)
                self._abort_if_unique_id_configured(updates={"host": self._host})
                if user_input["setup_method"] == "account":
                    return await self.async_step_account()
                return await self.async_step_manual_key()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_manual_key(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            local_key = user_input[CONF_LOCAL_KEY]
            try:
                blobs = await async_read_status(
                    self._host, self._device_id, local_key, timeout=DEFAULT_TIMEOUT
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Local key verification failed")
                errors["base"] = "invalid_key"
            else:
                if not any(len(b) == 151 for b in blobs):
                    errors["base"] = "no_status_report"
                else:
                    return self.async_create_entry(
                        title=f"Zee Refrigerator ({self._device_id[-6:]})",
                        data={
                            "host": self._host,
                            CONF_DEVICE_ID: self._device_id,
                            CONF_LOCAL_KEY: local_key,
                        },
                    )

        return self.async_show_form(
            step_id="manual_key", data_schema=STEP_MANUAL_KEY_SCHEMA, errors=errors
        )

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        default_zone = default_dial_code(self.hass.config.country)

        if user_input is not None:
            zone = str(user_input.get(CONF_ZONE_INFO, "")).strip().lstrip("+") or "0"
            try:
                cloud, result = await HaierCloud.login(
                    SEA_APP_CREDENTIALS,
                    user_input["login_id"],
                    user_input["password"],
                    zone_info=zone,
                    transport=async_cloud_transport(self.hass),
                )
            except CloudError as err:
                _LOGGER.exception("Haier cloud login failed")
                errors["base"] = "invalid_auth_detail"
                placeholders["detail"] = str(err)
            except (OSError, RuntimeError) as err:
                _LOGGER.exception("Haier cloud login errored")
                errors["base"] = "cannot_connect"
                placeholders["detail"] = str(err)
            else:
                creds = GatewayCreds.derive(
                    usdk_client_id=result.client_id, access_token=result.access_token
                )
                try:
                    local_key = await self.hass.async_add_executor_job(
                        partial(
                            get_localkey_via_gateway,
                            creds,
                            self._device_id,
                            timeout=GATEWAY_TIMEOUT,
                        )
                    )
                except (GatewayError, OSError, RuntimeError):
                    _LOGGER.exception("Gateway local key fetch failed")
                    errors["base"] = "key_fetch_failed"
                else:
                    return self.async_create_entry(
                        title=f"Zee Refrigerator ({self._device_id[-6:]})",
                        data={
                            "host": self._host,
                            CONF_DEVICE_ID: self._device_id,
                            CONF_LOCAL_KEY: local_key.key,
                            CONF_LOCALKEY_VERSION: local_key.version,
                            CONF_REFRESH_TOKEN: result.refresh_token,
                            CONF_ACCESS_TOKEN: result.access_token,
                            CONF_CLOUD_CLIENT_ID: result.client_id,
                            CONF_ZONE_INFO: str(result.raw.get("zoneInfo") or zone),
                        },
                    )

        return self.async_show_form(
            step_id="account",
            data_schema=_account_schema(default_zone),
            errors=errors,
            description_placeholders=placeholders or None,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HaierFridgeOptionsFlow:
        return HaierFridgeOptionsFlow()


class HaierFridgeOptionsFlow(config_entries.OptionsFlow):
    """Poll interval, manual re-key, or linking a Haier account after the fact."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            new_key = user_input.get(CONF_LOCAL_KEY)
            login_id = user_input.get("login_id")
            password = user_input.get("password")
            data = {**self.config_entry.data}

            if login_id and password:
                zone = (
                    str(user_input.get(CONF_ZONE_INFO, "")).strip().lstrip("+")
                    or self.config_entry.data.get(CONF_ZONE_INFO)
                    or default_dial_code(self.hass.config.country)
                    or "0"
                )
                try:
                    cloud, result = await HaierCloud.login(
                        SEA_APP_CREDENTIALS,
                        login_id,
                        password,
                        zone_info=zone,
                        transport=async_cloud_transport(self.hass),
                    )
                    creds = GatewayCreds.derive(
                        usdk_client_id=result.client_id, access_token=result.access_token
                    )
                    device_id = self.config_entry.data[CONF_DEVICE_ID]
                    local_key = await self.hass.async_add_executor_job(
                        partial(
                            get_localkey_via_gateway, creds, device_id, timeout=GATEWAY_TIMEOUT
                        )
                    )
                except (CloudError, GatewayError, OSError, RuntimeError):
                    _LOGGER.exception("Linking Haier account failed")
                    errors["base"] = "invalid_auth"
                else:
                    data.update(
                        {
                            CONF_LOCAL_KEY: local_key.key,
                            CONF_LOCALKEY_VERSION: local_key.version,
                            CONF_REFRESH_TOKEN: result.refresh_token,
                            CONF_ACCESS_TOKEN: result.access_token,
                            CONF_CLOUD_CLIENT_ID: result.client_id,
                            CONF_ZONE_INFO: str(result.raw.get("zoneInfo") or zone),
                        }
                    )
            elif new_key:
                device_id = self.config_entry.data[CONF_DEVICE_ID]
                host = self.config_entry.data["host"]
                try:
                    blobs = await async_read_status(
                        host, device_id, new_key, timeout=DEFAULT_TIMEOUT
                    )
                except Exception:  # noqa: BLE001
                    errors["base"] = "invalid_key"
                else:
                    if not any(len(b) == 151 for b in blobs):
                        errors["base"] = "no_status_report"
                    else:
                        data[CONF_LOCAL_KEY] = new_key

            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data
                )
                return self.async_create_entry(
                    title="",
                    data={
                        "scan_interval": user_input.get(
                            "scan_interval", DEFAULT_SCAN_INTERVAL
                        )
                    },
                )

        current_interval = self.config_entry.options.get(
            "scan_interval", DEFAULT_SCAN_INTERVAL
        )
        default_zone = (
            self.config_entry.data.get(CONF_ZONE_INFO)
            or default_dial_code(self.hass.config.country)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional("scan_interval", default=current_interval): int,
                    vol.Optional(CONF_LOCAL_KEY): str,
                    vol.Optional("login_id"): str,
                    vol.Optional("password"): str,
                    vol.Optional(CONF_ZONE_INFO, default=default_zone): _country_select(),
                }
            ),
            errors=errors,
        )
