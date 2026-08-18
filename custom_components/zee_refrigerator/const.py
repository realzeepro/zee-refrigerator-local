"""Constants for the Zee Refrigerator (local, monitoring-only) integration."""
from __future__ import annotations

DOMAIN = "zee_refrigerator"

CONF_LOCAL_KEY = "local_key"
CONF_DEVICE_ID = "device_id"
CONF_LOCALKEY_VERSION = "localkey_version"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_STATUS_LEN = "status_len"
CONF_LAYOUT = "layout"
CONF_MODEL = "model"

# Optional Haier cloud account, used only to auto-refresh the local key when it rotates.
# We store a durable refresh_token (minted at login), never the account password.
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_CLOUD_CLIENT_ID = "cloud_client_id"
CONF_ZONE_INFO = "zone_info"

GATEWAY_TIMEOUT = 8.0  # seconds; TLS connect + one round trip to the cloud MQTT gateway

DEFAULT_SCAN_INTERVAL = 30  # seconds; matches the fridge's single-session poll cadence
DEFAULT_TIMEOUT = 8.0  # seconds per read cycle

MANUFACTURER = "Haier"
# This layout was derived against a single unit. If your fridge reports
# different values, please open an issue with a raw status capture.
MODEL = "HRF-538TIFB1U1"

DEFAULT_STATUS_LEN = 151
