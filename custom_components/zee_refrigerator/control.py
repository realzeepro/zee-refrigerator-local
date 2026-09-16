"""Local control writes for the Zee Refrigerator.

The fridge accepts a single write mechanism locally over uSS/HRDP (port 56800):
one EPP frame per attribute, naming the attribute by its manufacturer-published
"eppCmd" and carrying the value in the payload. That is exactly Haier's own byte
map for this device class — not a group-set/grSetDAC, and not a cloud call.

Frame (built by the vendored ``build_epp_frame``):

    FF FF | len | 00*6 | frameType(0x01) | eppCmd(2) | value(2, big-endian) | checksum

The command ids and value encodings below come from the published byte map for
product ``BL046RE00`` / device class ``0102400W`` (the map's own name is
``0061801294CHNR``):

    refrigeratorTargetTempLevel  eppCmd 5D02   level 2..10      (2 = 1 °C ... 10 = 9 °C)
    energySavingStatus           eppCmd 5D30   true/false -> 1/0
    quickRefrigeratingMode       eppCmd 5D24   true/false -> 1/0   (速冷)
    quickFreezingMode            eppCmd 5D21   true/false -> 1/0   (速冻)
    intelligenceMode             eppCmd 5D20   true/false -> 1/0   (人工智慧)
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .const import TARGET_LEVEL_MAX, TARGET_LEVEL_MIN, WRITE_COMMANDS
from .vendor.haismart_hrdp import build_epp_frame

# The frame type every command is sent under (the app's control frame type). The
# fridge answers with a frameType 0x02 status report (accepted) or 0x03 (refused).
FRAME_TYPE_CONTROL = 0x01


def _encode_bool(value: Any) -> int:
    return 1 if value else 0


def _encode_level(value: Any) -> int:
    level = int(value)
    if not TARGET_LEVEL_MIN <= level <= TARGET_LEVEL_MAX:
        raise ValueError(
            f"target level {level} is outside the supported range "
            f"{TARGET_LEVEL_MIN}..{TARGET_LEVEL_MAX}"
        )
    return level


_ENCODERS: dict[str, Callable[[Any], int]] = {
    "target_level": _encode_level,
    "eco": _encode_bool,
    "super_cool": _encode_bool,
    "super_freeze": _encode_bool,
    "auto_set": _encode_bool,
}


def build_write_frame(name: str, value: Any) -> bytes:
    """The EPP frame that sets control ``name`` to ``value``.

    Raises ``ValueError`` for an unknown control or a value the fridge's own byte
    map does not publish — nothing is sent on the wire in that case.
    """
    epp_cmd = WRITE_COMMANDS.get(name)
    encoder = _ENCODERS.get(name)
    if epp_cmd is None or encoder is None:
        raise ValueError(f"unknown control {name!r}")
    raw = encoder(value)
    return build_epp_frame(
        FRAME_TYPE_CONTROL, bytes.fromhex(epp_cmd), raw.to_bytes(2, "big")
    )
