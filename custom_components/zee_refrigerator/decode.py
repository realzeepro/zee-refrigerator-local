"""Decode the Haier 538 IOT refrigerator's local status report.

The default layout targets the HRF-538TIFB1U1 (device_type 0102400W / product code
BL046RE00) — a fixed 151-byte report whose field offsets were identified by diffing
raw status captures against known app-side state changes (door open/close, Super
Freeze, Super Cool). It is NOT part of the upstream haismart-hrdp profile database,
which only knows AC report layouts.

Other Haier fridges will almost certainly use a different report length and/or
offsets. This decoder is therefore layout-driven: ``decode(blob, layout)`` reads
whatever offsets the layout specifies, applies each field's formula, and rejects
values that fall outside a field's plausibility bounds (so a wrong layout reports
"no decodable status" instead of silently wrong numbers). A user can paste a
capture-derived byte map in the integration's Options flow — no code changes
needed.

Byte map for the default 538 layout (0-indexed):
    92   fridge actual temp   = byte - 38          (°C)
    93   freezer actual temp  = byte - 38           (°C)
    98   fridge target temp   = (byte + 1) / 2       (°C)
    99   freezer target temp  = byte / 2 - 26        (°C)
    104  mode flags           bit2 = Eco
    105  mode flags           bit1 = Auto Set, bit3 = Super Freeze, bit4 = Super Cool
    107  door flags           bit0 = fridge door open, bit1 = freezer door open
    150  checksum (not decoded)
"""
from __future__ import annotations

from typing import Any, TypedDict

from .const import DEFAULT_STATUS_LEN

_LAYOUT_FIELDS = (
    "fridge_temp",
    "freezer_temp",
    "fridge_target",
    "freezer_target",
    "eco",
    "auto_set",
    "super_freeze",
    "super_cool",
    "fridge_door",
    "freezer_door",
)


def default_layout() -> dict[str, Any]:
    """The layout the HRF-538TIFB1U1 was tested with, as a fresh dict (never mutated)."""
    return {
        "status_len": DEFAULT_STATUS_LEN,
        "fridge_temp": {"offset": 92, "scale": 1.0, "shift": -38.0, "min": -60.0, "max": 60.0},
        "freezer_temp": {"offset": 93, "scale": 1.0, "shift": -38.0, "min": -60.0, "max": 30.0},
        "fridge_target": {"offset": 98, "scale": 0.5, "shift": 0.5, "min": -20.0, "max": 30.0},
        "freezer_target": {"offset": 99, "scale": 0.5, "shift": -26.0, "min": -40.0, "max": 15.0},
        "eco": {"offset": 104, "mask": 0x04},
        "auto_set": {"offset": 105, "mask": 0x02},
        "super_freeze": {"offset": 105, "mask": 0x08},
        "super_cool": {"offset": 105, "mask": 0x10},
        "fridge_door": {"offset": 107, "mask": 0x01},
        "freezer_door": {"offset": 107, "mask": 0x02},
    }


def build_layout(override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge a user-supplied byte map onto the default layout.

    ``override`` uses the same keys as the default layout. A numeric value means
    "same field, different offset" (``{"fridge_temp": 100}``); a dict is deep-merged
    (``{"fridge_temp": {"offset": 100, "min": -70}}``) so any unspecified part of the
    field spec keeps its default. ``status_len`` overrides the expected report length.
    """
    layout = default_layout()
    if not override:
        return layout
    if "status_len" in override:
        layout["status_len"] = int(override["status_len"])
    for name in _LAYOUT_FIELDS:
        if name not in override:
            continue
        user = override[name]
        if isinstance(user, dict):
            layout[name].update(user)
        else:
            layout[name]["offset"] = int(user)
    return layout


class FridgeStatus(TypedDict):
    fridge_temp_c: float
    freezer_temp_c: float
    fridge_target_c: float
    freezer_target_c: float
    fridge_door_open: bool
    freezer_door_open: bool
    eco: bool
    auto_set: bool
    super_freeze: bool
    super_cool: bool
    mode: str


# Priority order for the single "mode" reading: a boost mode wins over eco, eco over
# auto-set, and when none is active the fridge is in its normal/baseline state.
_MODE_PRIORITY = (
    ("super_freeze", "Super Freeze"),
    ("super_cool", "Super Cool"),
    ("eco", "Eco"),
    ("auto_set", "Auto Set"),
)


def _read_temp(blob: bytes, spec: dict[str, Any]) -> float | None:
    value = blob[spec["offset"]] * spec["scale"] + spec["shift"]
    if value < spec["min"] or value > spec["max"]:
        return None
    return float(value)


def _read_flag(blob: bytes, spec: dict[str, Any]) -> bool:
    return bool(blob[spec["offset"]] & spec["mask"])


def decode(
    blob: bytes, layout: dict[str, Any] | None = None
) -> FridgeStatus | None:
    """Decode a raw status blob with the given layout (default = the 538 layout).

    Returns ``None`` when the blob is not the layout's expected length, or when a
    temperature falls outside its plausibility bounds (a strong sign the layout does
    not match this model).
    """
    layout = layout or default_layout()
    if len(blob) != layout["status_len"]:
        return None

    fridge_temp = _read_temp(blob, layout["fridge_temp"])
    freezer_temp = _read_temp(blob, layout["freezer_temp"])
    fridge_target = _read_temp(blob, layout["fridge_target"])
    freezer_target = _read_temp(blob, layout["freezer_target"])
    if None in (fridge_temp, freezer_temp, fridge_target, freezer_target):
        return None

    flags = {
        "eco": _read_flag(blob, layout["eco"]),
        "auto_set": _read_flag(blob, layout["auto_set"]),
        "super_freeze": _read_flag(blob, layout["super_freeze"]),
        "super_cool": _read_flag(blob, layout["super_cool"]),
    }

    mode = next(
        (label for key, label in _MODE_PRIORITY if flags[key]),
        "Normal",
    )

    return FridgeStatus(
        fridge_temp_c=fridge_temp,
        freezer_temp_c=freezer_temp,
        fridge_target_c=fridge_target,
        freezer_target_c=freezer_target,
        fridge_door_open=_read_flag(blob, layout["fridge_door"]),
        freezer_door_open=_read_flag(blob, layout["freezer_door"]),
        eco=flags["eco"],
        auto_set=flags["auto_set"],
        super_freeze=flags["super_freeze"],
        super_cool=flags["super_cool"],
        mode=mode,
    )
