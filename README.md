# Haier Refrigerator — Home Assistant Integration (HACS)

A **HACS custom integration for Home Assistant** that monitors a **Haier 538 IOT
HRF-538TIFB1U1** refrigerator (Haismart / Haier U+ appliances) **locally** over the
uSS/HRDP protocol — **no cloud polling** after setup.

- **Read-only / monitoring:** temperatures, doors, and operating mode, straight from
  the fridge on your LAN.
- **No cloud dependency at runtime** — the fridge is polled directly over the local
  network; Haier's cloud is only used once (to fetch the local key) and to
  auto-refresh the key when it rotates.
- **Discoverable:** a supported Haier fridge is found automatically via DHCP and
  appears in Home Assistant's *Discovered* box.

> Also works with **other Haier fridge models** if their report layout differs: you
> can supply a byte map in the Options flow instead of needing a code change — see
> [Other fridge models](#other-fridge-models).

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

All entities live under one **device** in Home Assistant, and a full **diagnostics
download** is included for bug reports.

## Requirements

- Home Assistant with [HACS](https://hacs.xyz/) installed (Home Assistant 2024.1+)
- A Haier fridge that speaks the Haismart / uSS protocol on your LAN (tested model:
  HRF-538TIFB1U1)
- The fridge's **local IP address** — automatic if you let discovery find it, or
  assign a DHCP reservation (the key/session breaks if the IP changes)
- A **Haismart/Haier account** *(recommended — only needed for automatic key
  refresh; manual key entry works without one)*

## Installation

### Via HACS (custom repository)
1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/realzeepro/zee-refrigerator-local`, category **Integration**
3. Install **Zee Refrigerator (Local, Monitoring)**
4. Restart Home Assistant

### Manual
1. Copy `custom_components/zee_refrigerator/` into your HA `config/custom_components/`
2. Restart Home Assistant

## Setup

1. Settings → Devices & services → **+ Add integration** → search "Zee Refrigerator".
   If a supported fridge is on your network you can also just accept the
   **"Zee Refrigerator found"** discovery card — no IP typing needed.
2. Choose a setup method:
   - **Enter local key manually** — paste the fridge's current local key (see
     [Getting the local key](#getting-the-local-key)). Works immediately.
   - **Sign in with Haier account** — email/phone + password + the **country the
     account was registered in** (phone dialling code). Haier's server reports a
     wrong region as "account not registered", so pick the country the account was
     created in — not where you live or where the fridge is. The key is fetched
     automatically, and future key rotations are re-fetched automatically too.
3. Done — entities appear under one device.

## Getting the local key

The easiest path is the **account sign-in** above — no key required from you. If you
prefer to paste a key manually, you can obtain one with the Haismart app's ecosystem:

```
pip install 'haismart-extractor[cloud] @ git+https://github.com/enapt/haismart-local#subdirectory=packages/haismart-extractor'
haismart-keys --username you@example.com --region <your dialling code>
```

It signs in, lists every appliance on the account, and prints each one's device ID,
model and **local key**. Treat a local key as a secret — don't post it in bug
reports or forums.

## Options

Open **Settings → Devices & services → Zee Refrigerator → ⋮ → Options** to change:

- **Poll interval (seconds)** — how often the fridge is read (default 30; the fridge
  accepts one connection at a time).
- **New local key (manual re-key)** — paste a freshly re-fetched key after a
  rotation.
- **Haier account email/phone + password + country** — link an account to an
  existing entry so key rotations refresh automatically.
- **Advanced (other models):** **Status report length**, **Byte map (JSON)** and a
  **Model name** — see below.

## Other fridge models

The default layout is the HRF-538TIFB1U1's 151-byte status report. Other Haier
fridges almost certainly use a different report length and/or byte offsets. Rather
than failing silently with wrong numbers, the integration **validates readings**:
if a report decodes to implausible values it is rejected with a clear message.

If you have a different model and a raw status capture (from the diagnostics
download), you can adapt it without code:

1. In **Options**, set the **status report length** (bytes) to the length your unit
   reports (the poll error message shows the lengths it actually saw).
2. Set the **byte map** as JSON, e.g.:

   ```json
   {"fridge_temp": 92, "freezer_temp": 93, "fridge_target": 98, "freezer_target": 99,
    "eco": 104, "auto_set": 105, "super_freeze": 105, "super_cool": 105,
    "fridge_door": 107, "freezer_door": 107}
   ```

   Field values can be a plain offset (default formula applies) or an object for
   full control (`{"fridge_temp": {"offset": 92, "scale": 1, "shift": -38}}`).
3. Optionally set a **model name** to display on the device page.
4. Open an issue with your diagnostics so the layout can be added as a built-in.

## The local key rotates — and how this integration handles it

Haier's cloud periodically reassigns the fridge's local key. This integration
detects rotation — **it does not wait for a failure.** Every read includes the key
version the fridge is currently using; if that version doesn't match what this
integration holds, the read is refused *before* anything is decrypted
(garbage-from-a-stale-key never gets treated as real data).

What happens next depends on setup method:

- **Linked a Haier account (recommended):** the integration silently signs in
  (using a stored, reusable token — never your saved password), fetches the current
  key from Haier's cloud gateway, updates it in its own config entry, and retries
  the read. Nothing to do — it self-heals within one poll cycle.
- **Manual key entry:** there's no account to fetch a fresh key from, so a Home
  Assistant **repair issue** appears telling you the key rotated. Fix it under
  Settings → Devices & services → Zee Refrigerator → **Configure**, either by
  pasting a freshly re-fetched key, or by linking a Haier account there instead.

You can link an account at any time from the options flow (Configure), even if you
started with a manual key.

## Troubleshooting

**"Sign-in failed" / "Account is not registered"**
Almost always the **country/region**. It's the phone dialling code of the country
your Haier *account* was registered in, not where you live or where the fridge is.
hOn and Haier China accounts live on entirely different servers and no country code
will work.

**"No decodable status"**
The fridge answered but the report couldn't be decoded. Either the **local key is
stale** (re-key via Options, or link an account), or the **report layout differs**
from the default (see [Other fridge models](#other-fridge-models)).

**Fridge moved to a new IP**
Keep the IP stable with a DHCP reservation — the key/session is tied to the address.

**Temperatures look wrong**
Check the fridge's actual readings in the Haismart app. If they disagree with the
integration, grab a diagnostics download and open an issue.

## Diagnostics

Settings → Devices & services → Zee Refrigerator → ⋮ → **Download diagnostics**.
This includes the last raw status hex, the active byte map, and the decoded values —
everything needed to extend or fix the layout for your model.

## How the status layout was found

The layout for the HRF-538TIFB1U1 (device_type `0102400W` / product code
`BL046RE00`) was identified by taking multiple raw status captures, changing one
setting at a time in the Haismart app (door open/close, Super Freeze, Super Cool),
and diffing the bytes across captures to isolate which byte/bit changed.

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

This was mapped against **one physical unit**. If your fridge reports different
values, please open an issue with a raw status hex dump.

## Credits

Local protocol transport (`vendor/haismart_hrdp/`) and the cloud/gateway client used
for key auto-refresh (`vendor/haismart_extractor/`) are vendored from
[enapt/haismart-local](https://github.com/enapt/haismart-local) (MIT).
Fridge-specific status layout derived independently for this project.

## License

MIT — see [LICENSE](./LICENSE).