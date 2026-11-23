"""Tests for the Samsung AC protocol against captures of a real remote.

Runs with pytest, or with plain ``python tests/test_protocol.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(
    0, str(Path(__file__).parents[1] / "custom_components" / "samsung_infrared_plus")
)

import protocol as p  # noqa: E402

CAPTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "captures.json").read_text(encoding="utf-8")
)["captures"]

M, F, S, X = p.Mode, p.Fan, p.Swing, p.Special

# label: (power, mode, temperature, fan as sent, swing, special)
EXPECTED = {
    "ligar (frio 24 auto)": (True, M.AUTO, 24, F.AUTO, S.OFF, X.NONE),
    "desligar": (False, M.AUTO, 24, F.AUTO, S.OFF, X.NONE),
    "modo frio 24": (True, M.COOL, 24, F.HIGH, S.OFF, X.NONE),
    "modo quente 24": (True, M.HEAT, 24, F.AUTO, S.OFF, X.NONE),
    "modo desumidificar": (True, M.DRY, 23, F.AUTO, S.OFF, X.NONE),
    "modo ventilar": (True, M.FAN_ONLY, 24, F.MEDIUM, S.OFF, X.NONE),
    "modo auto": (True, M.AUTO, 24, F.AUTO, S.OFF, X.NONE),
    "frio 16": (True, M.COOL, 16, F.HIGH, S.OFF, X.NONE),
    "frio 17": (True, M.COOL, 17, F.HIGH, S.OFF, X.NONE),
    "frio 18": (True, M.COOL, 18, F.HIGH, S.OFF, X.NONE),
    "frio 23": (True, M.COOL, 23, F.HIGH, S.OFF, X.NONE),
    "frio 24": (True, M.COOL, 24, F.HIGH, S.OFF, X.NONE),
    "frio 25": (True, M.COOL, 25, F.HIGH, S.OFF, X.NONE),
    "frio 30": (True, M.COOL, 30, F.HIGH, S.OFF, X.NONE),
    "ventilador auto": (True, M.COOL, 16, F.AUTO, S.OFF, X.NONE),
    "ventilador baixo": (True, M.COOL, 16, F.LOW, S.OFF, X.NONE),
    "ventilador médio": (True, M.COOL, 16, F.MEDIUM, S.OFF, X.NONE),
    "ventilador alto": (True, M.COOL, 16, F.HIGH, S.OFF, X.NONE),
    "ventilador turbo": (True, M.COOL, 16, F.TURBO, S.OFF, X.NONE),
    "swing vertical ligado": (True, M.COOL, 16, F.TURBO, S.VERTICAL, X.NONE),
    "swing vertical desligado": (True, M.COOL, 16, F.TURBO, S.OFF, X.NONE),
    "swing horizontal ligado": (True, M.COOL, 16, F.TURBO, S.HORIZONTAL, X.NONE),
    "swing horizontal desligado": (True, M.COOL, 16, F.TURBO, S.OFF, X.NONE),
    "Fast on": (True, M.COOL, 16, F.TURBO, S.OFF, X.FAST),
    "Fast off": (True, M.COOL, 16, F.TURBO, S.OFF, X.NONE),
    "Windfree on": (True, M.COOL, 16, F.AUTO, S.OFF, X.WINDFREE),
    "Windfree off": (True, M.COOL, 16, F.TURBO, S.OFF, X.NONE),
}


def _state(capture: dict) -> p.SamsungAcState:
    state = p.decode_timings(capture["timings"])
    assert state is not None, capture["label"]
    return state


def test_every_capture_has_an_expectation() -> None:
    assert {c["label"] for c in CAPTURES} == set(EXPECTED)
    assert len(CAPTURES) == 27


def test_decodes_real_captures() -> None:
    for capture in CAPTURES:
        state = _state(capture)
        power, mode, temp, fan, swing, special = EXPECTED[capture["label"]]
        got = (state.power, state.mode, state.temperature, state.effective_fan,
               state.swing, state.special)
        assert got == (power, mode, temp, fan, swing, special), capture["label"]


def test_decodes_with_header() -> None:
    for capture in CAPTURES:
        timings = [p.HDR_MARK, -p.HDR_SPACE, *capture["timings"]]
        assert p.decode_timings(timings) == _state(capture), capture["label"]


def test_reencodes_bit_for_bit() -> None:
    """Encoding a decoded state rebuilds exactly what the remote sent."""
    for capture in CAPTURES:
        sent = bytes.fromhex(capture["bytes"])
        rebuilt = p.encode_frame(_state(capture), extended=len(sent) == 21)
        assert rebuilt == sent, (capture["label"], rebuilt.hex(" "), sent.hex(" "))


def test_round_trip_all_states() -> None:
    for power in (True, False):
        for mode in M:
            for temp in range(p.MIN_TEMP, p.MAX_TEMP + 1):
                for fan in F:
                    for swing in S:
                        for special in X:
                            state = p.SamsungAcState(power, mode, temp, fan, swing, special)
                            for extended in (True, False):
                                frame = p.encode_frame(state, extended=extended)
                                decoded = p.decode_timings(p.encode_timings(frame))
                                assert decoded is not None
                                assert decoded.power == power
                                assert decoded.mode == mode
                                assert decoded.temperature == temp
                                assert decoded.swing == swing
                                assert decoded.special == special
                                assert decoded.effective_fan == state.effective_fan


def test_matches_core_library_frames() -> None:
    """Frames the core's SamsungAC0292Command sends (its test vectors) still decode."""
    vectors = {
        "02 92 0F 00 00 00 F0 01 D2 0F 00 00 00 00 01 E2 FE 71 80 11 F0": (M.COOL, 24, F.AUTO, S.OFF),
        "02 92 0F 00 00 00 F0 01 D2 0F 00 00 00 00 01 D2 FE 71 80 15 F0": (M.COOL, 24, F.LOW, S.OFF),
        "02 92 0F 00 00 00 F0 01 D2 0F 00 00 00 00 01 E2 FE 71 80 41 F0": (M.HEAT, 24, F.AUTO, S.OFF),
        "02 92 0F 00 00 00 F0 01 D2 0F 00 00 00 00 01 E2 AE 71 90 19 F0": (M.COOL, 25, F.MEDIUM, S.VERTICAL),
    }
    for hexstr, (mode, temp, fan, swing) in vectors.items():
        frame = bytes.fromhex(hexstr)
        state = p.decode_timings(p.encode_timings(frame))
        assert state is not None and state.power
        assert (state.mode, state.temperature, state.fan, state.swing) == (mode, temp, fan, swing)
        assert p.encode_frame(state) == frame


def test_rejects_other_signals() -> None:
    sample = CAPTURES[2]["timings"]
    assert p.decode_timings([]) is None
    assert p.decode_timings([p.HDR_MARK, -p.HDR_SPACE]) is None  # header fragment
    assert p.decode_timings(sample[:100]) is None  # truncated
    assert p.decode_timings([9000, -4500] + [560, -560] * 32 + [560]) is None  # NEC
    corrupt = list(sample)
    corrupt[201] = -1432 if abs(corrupt[201]) < 900 else -436  # flip one data bit (a space)
    assert p.decode_sections(corrupt) is not None  # still well-formed timings...
    assert p.decode_timings(corrupt) is None  # ...but the checksum catches it


def test_temperature_validation() -> None:
    for bad in (15, 31):
        try:
            p.SamsungAcState(temperature=bad)
        except ValueError:
            continue
        raise AssertionError(bad)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, func in tests:
        func()
        print("ok", name)
    print(f"{len(tests)} testes passaram")
