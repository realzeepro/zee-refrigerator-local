# Zee Refrigerator — Local Home Assistant Integration (Monitoring)

A HACS custom integration for monitoring a **Haier 538 IOT HRF-538TIFB1U1** refrigerator
(and possibly other units in the same `0102400W` device family / `BL046RE00`
product code) locally in Home Assistant — no cloud polling required after setup.

It talks directly to the fridge over Haier's local **uSS/HRDP** protocol
(port 56800), decoding a status report layout that was reverse-engineered
specifically for this fridge.

## ⚠️ Read-only / monitoring only

This integration **does not support control**. The fridge's firmware does not
honour local writes for this device family — every local write framing tried
(binary group-set, JSON attribute write, multiple sequence-number sweeps) was
silently ignored. Cloud control (MQTT / WebSocket) was also not confirmed working.

Use the Haismart app to change settings; use this integration to see the results
in Home Assistant.

## What you get

**Sensors**
- Fridge temperature
- Freezer temperature
- Fridge target temperature
- Freezer target temperature
- Mode — which operating mode the fridge is in (`Normal` / `Eco` / `Auto Set` / `Super Freeze` / `Super Cool`)

**Binary sensors**
- Fridge door (open/closed)
- Freezer door (open/closed)
- Eco mode
- Auto Set mode
- Super Freeze
- Super Cool

## Requirements

- Home Assistant with HACS installed
- The fridge's **local IP address** (assign it a DHCP reservation — the key/session
  breaks if the IP changes)
- The fridge's **current local key** (see below — it rotates periodically)
- A Haismart/Haier account *(recommended — only needed for automatic key refresh; manual key entry works without one)*

## Installation

### Via HACS (custom repository)
1. HACS → Integrations → ⋮ → Custom repositories
2. Add this repo's URL, category **Integration**
3. Install **Zee Refrigerator (Local, Monitoring)**
4. Restart Home Assistant

### Manual
1. Copy `custom_components/zee_refrigerator/` into your HA `config/custom_components/`
2. Restart Home Assistant

## Setup

1. Settings → Devices & services → **+ Add integration** → search "Zee Refrigerator"
2. Enter the fridge's local IP, then choose a setup method:
   - **Enter local key manually** — paste the current key. Works immediately.
   - **Sign in with Haier account** — email/phone + password + the **country the account was
     registered in** (phone dialling code; Haier's server reports a wrong region as "account not
     registered", so pick the country the account was created in, not where you live or where the
     fridge is). The key is fetched automatically, and (unlike manual setup) future key rotations
     are re-fetched automatically too — see below.
3. Done — entities appear under one device

## The local key rotates — and how this integration handles it

Haier's cloud periodically reassigns the fridge's local key. This integration
detects rotation — **it does not wait for a failure.** Every read includes the key
version the fridge is currently using; if that version doesn't match what
this integration holds, the read is refused *before* anything is decrypted
(garbage-from-a-stale-key never gets treated as real data).

What happens next depends on setup method:

- **Linked a Haier account (recommended):** the integration silently signs in
  (using a stored, reusable token — never your saved password), fetches the
  current key from Haier's cloud gateway, updates it in its own config entry,
  and retries the read. Nothing to do — it self-heals within one poll cycle.
- **Manual key entry:** there's no account to fetch a fresh key from, so a
  Home Assistant **repair issue** appears telling you the key rotated. Fix it
  under Settings → Devices & services → Zee Refrigerator → **Configure**, either
  by pasting a freshly re-fetched key, or by linking a Haier account there
  instead (switches you onto the self-healing path going forward).

You can link an account at any time from the options flow (Configure), even
if you started with a manual key.

## How the status layout was found

The fridge's cloud "digital model" (fetched during pairing) already exposes
named, human-readable attributes — `refrigeratorTemperatureC`,
`freezerDoorStatus`, `quickFreezingMode`, etc. — but those values are a
one-time snapshot taken at pairing, not live-polled. The **live** data comes
from the raw 151-byte local status blob, which is a fixed byte-offset report
(same style as Haier's AC reports, different layout).

The layout below was found by taking multiple status captures, changing one
setting at a time in the Haismart app (door open/close, Super Freeze, Super
Cool), waiting for a poll cycle (~30s), and diffing the raw bytes across
captures to isolate which byte/bit changed for which setting.

| Byte | Field | Decode |
|---|---|---|
| 92 | Fridge actual temp | `byte − 38` °C |
| 93 | Freezer actual temp | `byte − 38` °C |
| 98 | Fridge target temp | `(byte + 1) / 2` °C |
| 99 | Freezer target temp | `byte / 2 − 26` °C |
| 104 | Mode flags | bit2 = Eco |
| 105 | Mode flags | bit1 = Auto Set, bit3 = Super Freeze, bit4 = Super Cool |
| 107 | Door flags | bit0 = fridge door, bit1 = freezer door |
| 150 | Checksum | not decoded |

This was reverse-engineered against **one physical unit**. If your fridge
reports different values, please open an issue with a raw status hex dump —
you can get one from the integration's diagnostics download
(Settings → Devices & services → Zee Refrigerator → ⋮ → Download diagnostics).

## Credits

Local protocol transport (`vendor/haismart_hrdp/`) and the cloud/gateway client
used for key auto-refresh (`vendor/haismart_extractor/`) are vendored from
[enapt/haismart-local](https://github.com/enapt/haismart-local) (MIT).
Fridge-specific status layout reverse-engineered independently for this project.

## License

MIT — see [LICENSE](./LICENSE).
