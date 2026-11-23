"""Samsung air conditioner infrared protocol (the "02 92" family).

Pure Python, with no Home Assistant imports, so it can be tested on its own.

Frame layout, mapped from captures of a real Samsung remote (see
``tests/fixtures/captures.json``) and cross-checked against IRremoteESP8266
(``SAMSUNG_AC``) and ``infrared_protocols.commands.samsung_ac``:

* timings: optional header (690us mark, 17844us space), then 2 or 3 sections;
  each section is a 3086us/8864us leader, 56 bits sent LSB first (586us mark
  followed by a 436us space for 0 or 1432us for 1) and a 586us trailer mark,
  followed by a 2886us gap between sections.
* the remote sends 14 bytes (section 1 + state section) for ordinary key
  presses and 21 bytes (section 1 + section 2 + state section) to power the
  unit on or off.

State section (7 bytes)::

    byte 0      0x01
    byte 1      bits 0-3: 0x2; bits 4-7: checksum low nibble
    byte 2      bits 0-3: checksum high nibble; bits 4-7: swing
    byte 3      bits 1-3: special fan mode (Fast / WindFree); 0x71 otherwise
    byte 4      bits 4-7: temperature - 16
    byte 5      bit 0: 1; bits 1-3: fan; bits 4-6: mode; bit 7: set in auto
    byte 6      bits 4-7: 0xF on, 0xC off
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

MIN_TEMP = 16
MAX_TEMP = 30


class Mode(IntEnum):
    """HVAC mode, byte 5 bits 4-6 of the state section."""

    AUTO = 0
    COOL = 1
    DRY = 2
    FAN_ONLY = 3
    HEAT = 4


class Fan(IntEnum):
    """Fan speed, byte 5 bits 1-3 of the state section."""

    AUTO = 0
    LOW = 2
    MEDIUM = 4
    HIGH = 5
    TURBO = 7


class Swing(IntEnum):
    """Swing, byte 2 bits 4-6 of the state section (bit 7 is always set)."""

    VERTICAL = 0x2
    HORIZONTAL = 0x3
    BOTH = 0x4  # from IRremoteESP8266; not seen in captures yet
    OFF = 0x7


class Special(IntEnum):
    """Special fan mode, byte 3 bits 1-3 of the state section."""

    NONE = 0b000
    FAST = 0b011
    WINDFREE = 0b101


# Fan speed each special mode forces, as the remote sends it.
SPECIAL_FAN = {Special.FAST: Fan.TURBO, Special.WINDFREE: Fan.AUTO}


@dataclass(frozen=True)
class SamsungAcState:
    """Everything one frame carries; every frame carries the whole state."""

    power: bool = False
    mode: Mode = Mode.COOL
    temperature: int = 24
    fan: Fan = Fan.AUTO
    swing: Swing = Swing.OFF
    special: Special = Special.NONE

    def __post_init__(self) -> None:
        """Validate the temperature."""
        if not MIN_TEMP <= self.temperature <= MAX_TEMP:
            raise ValueError(
                f"temperature {self.temperature} out of range {MIN_TEMP}..{MAX_TEMP}"
            )

    @property
    def effective_fan(self) -> Fan:
        """Return the fan speed the frame carries.

        Auto mode and the special modes force a fan speed of their own.
        """
        if self.mode is Mode.AUTO:
            return Fan.AUTO
        return SPECIAL_FAN.get(self.special, self.fan)


# ---------------------------------------------------------------- bytes
SECTION_LEN = 7
SECTION1_ON = bytes.fromhex("02920F000000F0")
SECTION1_OFF = bytes.fromhex("02B20F000000C0")
SECTION2 = bytes.fromhex("01D20F00000000")

_BYTE3_BASE = 0x71


def section_checksum(section: bytes | bytearray) -> int:
    """Return the checksum of a 7-byte section (inverted count of set bits)."""
    total = (
        bin(section[0]).count("1")
        + bin(section[1] & 0x0F).count("1")
        + bin(section[2] >> 4).count("1")
        + sum(bin(byte).count("1") for byte in section[3:7])
    )
    return (total ^ 0xFF) & 0xFF


def _stored_checksum(section: bytes | bytearray) -> int:
    return ((section[2] & 0x0F) << 4) | (section[1] >> 4)


def _with_checksum(section: bytearray) -> bytes:
    checksum = section_checksum(section)
    section[1] = (section[1] & 0x0F) | ((checksum & 0x0F) << 4)
    section[2] = (section[2] & 0xF0) | (checksum >> 4)
    return bytes(section)


def encode_state_section(state: SamsungAcState) -> bytes:
    """Build the state section for a state."""
    section = bytearray(SECTION_LEN)
    section[0] = 0x01
    section[1] = 0x02
    section[2] = (0x8 | state.swing) << 4
    section[3] = _BYTE3_BASE | (state.special << 1)
    section[4] = (state.temperature - MIN_TEMP) << 4
    section[5] = 0x01 | (state.effective_fan << 1) | (state.mode << 4)
    if state.power and state.mode is Mode.AUTO:
        # The remote sets bit 7 in auto mode, but not in the power-off frame.
        section[5] |= 0x80
    section[6] = 0xF0 if state.power else 0xC0
    return _with_checksum(section)


def encode_frame(state: SamsungAcState, *, extended: bool = True) -> bytes:
    """Build the bytes of a frame.

    ``extended`` builds the 21-byte frame the remote sends to power the unit on
    or off; a frame turning the unit off is always extended.
    """
    state_section = encode_state_section(state)
    if not state.power:
        return SECTION1_OFF + SECTION2 + state_section
    if extended:
        return SECTION1_ON + SECTION2 + state_section
    return SECTION1_ON + state_section


# ---------------------------------------------------------------- timings
HDR_MARK = 690
HDR_SPACE = 17844
SECTION_MARK = 3086
SECTION_SPACE = 8864
BIT_MARK = 586
ONE_SPACE = 1432
ZERO_SPACE = 436
SECTION_GAP = 2886
FINAL_GAP = 30000


def encode_timings(frame: bytes) -> list[int]:
    """Encode frame bytes into raw timings (+mark / -space, microseconds)."""
    timings = [HDR_MARK, -HDR_SPACE]
    for offset in range(0, len(frame), SECTION_LEN):
        timings += [SECTION_MARK, -SECTION_SPACE]
        for byte in frame[offset : offset + SECTION_LEN]:
            for bit in range(8):
                timings += [BIT_MARK, -(ONE_SPACE if byte >> bit & 1 else ZERO_SPACE)]
        last = offset + SECTION_LEN >= len(frame)
        timings += [BIT_MARK, -(FINAL_GAP if last else SECTION_GAP)]
    return timings


def _close(value: int, expected: int, tolerance: float) -> bool:
    return abs(value - expected) <= expected * tolerance


def decode_sections(timings: list[int]) -> list[bytes] | None:
    """Split raw timings into 7-byte sections.

    The header is optional: receivers that end a capture on the long header
    space hand it over as a separate signal.
    """
    values = [abs(value) for value in timings]
    idx = 0
    if len(values) >= 2 and _close(values[0], HDR_MARK, 0.35) and _close(
        values[1], HDR_SPACE, 0.25
    ):
        idx = 2
    sections: list[bytes] = []
    while idx + 1 < len(values):
        if not (
            _close(values[idx], SECTION_MARK, 0.3)
            and _close(values[idx + 1], SECTION_SPACE, 0.25)
        ):
            break
        idx += 2
        section = bytearray()
        for _ in range(SECTION_LEN):
            byte = 0
            for bit in range(8):
                if idx + 1 >= len(values):
                    return None
                mark, space = values[idx], values[idx + 1]
                if abs(mark - BIT_MARK) > 300:
                    return None
                if abs(space - ZERO_SPACE) <= 300:
                    pass
                elif abs(space - ONE_SPACE) <= 400:
                    byte |= 1 << bit
                else:
                    return None
                idx += 2
            section.append(byte)
        sections.append(bytes(section))
        # Trailer mark, then the gap before the next section (may be missing
        # after the last one).
        if idx >= len(values) or abs(values[idx] - BIT_MARK) > 300:
            return None
        idx += 2
    return sections or None


def decode_state_section(section: bytes) -> SamsungAcState | None:
    """Decode a state section, or return None if it does not look like one."""
    if (
        len(section) != SECTION_LEN
        or section[0] != 0x01
        or section[1] & 0x0F != 0x02
        or not section[5] & 0x01
        or _stored_checksum(section) != section_checksum(section)
    ):
        return None
    power_nibble = section[6] >> 4
    if power_nibble not in (0xF, 0xC):
        return None
    try:
        swing = Swing((section[2] >> 4) & 0x7)
        special = Special((section[3] >> 1) & 0x7)
        mode = Mode((section[5] >> 4) & 0x7)
        fan = Fan((section[5] >> 1) & 0x7)
    except ValueError:
        return None
    temperature = (section[4] >> 4) + MIN_TEMP
    if temperature > MAX_TEMP:
        return None
    return SamsungAcState(
        power=power_nibble == 0xF,
        mode=mode,
        temperature=temperature,
        fan=fan,
        swing=swing,
        special=special,
    )


def decode_timings(timings: list[int]) -> SamsungAcState | None:
    """Decode raw timings from a receiver into the state the remote sent."""
    sections = decode_sections(timings)
    if sections is None or len(sections) not in (2, 3):
        return None
    first, state_section = sections[0], sections[-1]
    if first not in (SECTION1_ON, SECTION1_OFF):
        return None
    if len(sections) == 3 and sections[1] != SECTION2:
        return None
    state = decode_state_section(state_section)
    if state is None or state.power != (first == SECTION1_ON):
        return None
    return state

