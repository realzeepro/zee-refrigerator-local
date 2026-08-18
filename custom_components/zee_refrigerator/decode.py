"""Decode the Haier HRF-538TIFB1U1's 151-byte local status report.

This layout was reverse-engineered by diffing raw status captures against known
app-side state changes (door open/close, Super Freeze, Super Cool). It is specific
to this fridge's device_type (0102400W / product_code BL046RE00) and is NOT part of
the upstream haismart-hrdp profile database, which only knows AC report layouts.

If your fridge reports different numbers than the Haismart app, please open an
issue on the integration's repo with a raw status hex dump (see diagnostics).

Byte map (0-indexed):
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

from typing import TypedDict

from .const import STATUS_LEN


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


def decode(blob: bytes) -> FridgeStatus | None:
    """Decode a raw status blob. Returns None if the blob isn't a 151-byte status report."""
    if len(blob) != STATUS_LEN:
        return None

    mode_flags_104 = blob[104]
    mode_flags_105 = blob[105]
    door_flags = blob[107]

    flags = {
        "eco": bool(mode_flags_104 & 0b0100),
        "auto_set": bool(mode_flags_105 & 0b0010),
        "super_freeze": bool(mode_flags_105 & 0b1000),
        "super_cool": bool(mode_flags_105 & 0b10000),
    }

    mode = next(
        (label for key, label in _MODE_PRIORITY if flags[key]),
        "Normal",
    )

    return FridgeStatus(
        fridge_temp_c=float(blob[92] - 38),
        freezer_temp_c=float(blob[93] - 38),
        fridge_target_c=(blob[98] + 1) / 2,
        freezer_target_c=blob[99] / 2 - 26,
        fridge_door_open=bool(door_flags & 0b0001),
        freezer_door_open=bool(door_flags & 0b0010),
        eco=flags["eco"],
        auto_set=flags["auto_set"],
        super_freeze=flags["super_freeze"],
        super_cool=flags["super_cool"],
        mode=mode,
    )
