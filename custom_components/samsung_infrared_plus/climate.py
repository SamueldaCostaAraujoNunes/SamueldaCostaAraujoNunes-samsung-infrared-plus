"""Climate platform for Samsung Infrared Plus.

Unlike the core ``samsung_infrared`` climate, this one encodes the frames with
its own codec (``protocol.py``), which supports horizontal swing, the turbo fan
speed and the Fast and WindFree modes, and can follow a physical remote
through an optional infrared receiver.
"""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import Any, override

from infrared_protocols.commands import Command

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_BOOST,
    PRESET_NONE,
    SWING_OFF,
    SWING_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.infrared import (
    InfraredEmitterConsumerEntity,
    InfraredReceivedSignal,
    InfraredReceiverConsumerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import (
    CONF_DEVICE_TYPE,
    CONF_INFRARED_EMITTER_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
    SamsungDeviceType,
)
from .entity import SamsungIrEntity
from .protocol import (
    MAX_TEMP,
    MIN_TEMP,
    Fan,
    Mode,
    SamsungAcState,
    Special,
    Swing,
    decode_timings,
    encode_frame,
    encode_timings,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

FAN_TURBO = "turbo"
PRESET_WINDFREE = "windfree"

_HA_TO_MODE: dict[HVACMode, Mode] = {
    HVACMode.AUTO: Mode.AUTO,
    HVACMode.COOL: Mode.COOL,
    HVACMode.DRY: Mode.DRY,
    HVACMode.FAN_ONLY: Mode.FAN_ONLY,
    HVACMode.HEAT: Mode.HEAT,
}
_MODE_TO_HA = {mode: ha for ha, mode in _HA_TO_MODE.items()}

_HA_TO_FAN: dict[str, Fan] = {
    FAN_AUTO: Fan.AUTO,
    FAN_LOW: Fan.LOW,
    FAN_MEDIUM: Fan.MEDIUM,
    FAN_HIGH: Fan.HIGH,
    FAN_TURBO: Fan.TURBO,
}
_FAN_TO_HA = {fan: ha for ha, fan in _HA_TO_FAN.items()}

_HA_TO_SPECIAL: dict[str, Special] = {
    PRESET_NONE: Special.NONE,
    PRESET_BOOST: Special.FAST,  # shown as "Fast"
    PRESET_WINDFREE: Special.WINDFREE,
}
_SPECIAL_TO_HA = {special: ha for ha, special in _HA_TO_SPECIAL.items()}

# (vertical, horizontal) <-> swing field
_SWING_FLAGS: dict[Swing, tuple[bool, bool]] = {
    Swing.OFF: (False, False),
    Swing.VERTICAL: (True, False),
    Swing.HORIZONTAL: (False, True),
    Swing.BOTH: (True, True),
}
_FLAGS_TO_SWING = {flags: swing for swing, flags in _SWING_FLAGS.items()}


class SamsungAcCommand(Command):
    """Infrared command carrying one Samsung AC frame."""

    def __init__(self, frame: bytes, *, modulation: int = 38000) -> None:
        """Initialize the command."""
        super().__init__(modulation=modulation, repeat_count=0)
        self.frame = frame

    @override
    def get_raw_timings(self) -> list[int]:
        """Return the raw timings of the frame."""
        return encode_timings(self.frame)


class _StoredAcState(ExtraStoredData):
    """The whole assumed state, restored across restarts.

    The visible state alone is not enough: while the unit is off it does not
    show the mode or the fan speed the next power-on frame has to carry.
    """

    def __init__(self, state: SamsungAcState) -> None:
        self.state = state

    @override
    def as_dict(self) -> dict[str, Any]:
        state = self.state
        return {
            "power": state.power,
            "mode": state.mode.name,
            "temperature": state.temperature,
            "fan": state.fan.name,
            "swing": state.swing.name,
            "special": state.special.name,
        }

    @staticmethod
    def state_from_dict(data: dict[str, Any]) -> SamsungAcState | None:
        try:
            return SamsungAcState(
                power=bool(data["power"]),
                mode=Mode[data["mode"]],
                temperature=int(data["temperature"]),
                fan=Fan[data["fan"]],
                swing=Swing[data["swing"]],
                special=Special[data["special"]],
            )
        except (KeyError, TypeError, ValueError):
            return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Samsung AC climate entity from a config entry."""
    if entry.data[CONF_DEVICE_TYPE] != SamsungDeviceType.AC:
        return

    emitter_entity_id = entry.data[CONF_INFRARED_EMITTER_ENTITY_ID]
    if receiver_entity_id := entry.data.get(CONF_INFRARED_RECEIVER_ENTITY_ID):
        async_add_entities(
            [SamsungIrClimateWithReceiver(entry, emitter_entity_id, receiver_entity_id)]
        )
    else:
        async_add_entities([SamsungIrClimate(entry, emitter_entity_id)])


class SamsungIrClimate(
    SamsungIrEntity, InfraredEmitterConsumerEntity, RestoreEntity, ClimateEntity
):
    """Samsung AC controlled through an infrared emitter."""

    _attr_name = None
    _attr_translation_key = "samsung_ac"
    _attr_assumed_state = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = float(MIN_TEMP)
    _attr_max_temp = float(MAX_TEMP)
    _attr_hvac_modes = [HVACMode.OFF, *_HA_TO_MODE]
    _attr_fan_modes = list(_HA_TO_FAN)
    _attr_swing_modes = [SWING_OFF, SWING_ON]
    _attr_swing_horizontal_modes = [SWING_OFF, SWING_ON]
    _attr_preset_modes = list(_HA_TO_SPECIAL)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.SWING_HORIZONTAL_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, entry: ConfigEntry, emitter_entity_id: str) -> None:
        """Initialize the climate entity."""
        super().__init__(entry, unique_id_suffix="climate", device_name="Samsung AC")
        self._infrared_emitter_entity_id = emitter_entity_id
        # Assumed state of the unit. ``mode`` keeps the last active mode while
        # the unit is off, and ``fan`` keeps the speed chosen by the user even
        # while auto mode or a special mode forces another one into the frame.
        self._ac = SamsungAcState()

    # ------------------------------------------------------------ state
    @property
    @override
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return _MODE_TO_HA[self._ac.mode] if self._ac.power else HVACMode.OFF

    @property
    @override
    def target_temperature(self) -> float:
        """Return the target temperature."""
        return float(self._ac.temperature)

    @property
    @override
    def fan_mode(self) -> str:
        """Return the fan speed the unit runs at."""
        return _FAN_TO_HA[self._ac.effective_fan]

    @property
    @override
    def swing_mode(self) -> str:
        """Return the vertical swing."""
        return SWING_ON if _SWING_FLAGS[self._ac.swing][0] else SWING_OFF

    @property
    @override
    def swing_horizontal_mode(self) -> str:
        """Return the horizontal swing."""
        return SWING_ON if _SWING_FLAGS[self._ac.swing][1] else SWING_OFF

    @property
    @override
    def preset_mode(self) -> str:
        """Return the special mode."""
        return _SPECIAL_TO_HA[self._ac.special]

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the assumed state, as infrared cannot read it back."""
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None and (
            state := _StoredAcState.state_from_dict(extra.as_dict())
        ) is not None:
            self._ac = state

    @property
    @override
    def extra_restore_state_data(self) -> _StoredAcState:
        """Return the state to restore after a restart."""
        return _StoredAcState(self._ac)

    # ------------------------------------------------------------ sending
    async def _async_apply(self, *, send: bool = True, **changes: Any) -> None:
        """Apply changes to the assumed state and send the resulting frame.

        While the unit is off a change is only recorded: the next power-on
        frame carries it, as with the physical remote. An explicit power change
        is always sent, so turning off works even if the assumed state is wrong.
        """
        new_state = replace(self._ac, **changes)
        if send and (new_state.power or "power" in changes):
            # Always the 21-byte frame, like the core integration: it also powers
            # the unit on if it was turned off behind Home Assistant's back.
            await self._send_command(SamsungAcCommand(encode_frame(new_state)))
        self._ac = new_state
        self.async_write_ha_state()

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._async_apply(power=False)
        else:
            await self._async_apply(power=True, mode=_HA_TO_MODE[hvac_mode])

    @override
    async def async_turn_on(self) -> None:
        """Turn on in the last active mode."""
        await self._async_apply(power=True)

    @override
    async def async_turn_off(self) -> None:
        """Turn off."""
        await self._async_apply(power=False)

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature, and the HVAC mode when one is given."""
        changes: dict[str, Any] = {}
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            changes["temperature"] = max(MIN_TEMP, min(MAX_TEMP, round(temperature)))
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            if hvac_mode == HVACMode.OFF:
                changes["power"] = False
            else:
                changes |= {"power": True, "mode": _HA_TO_MODE[HVACMode(hvac_mode)]}
        if changes:
            await self._async_apply(**changes)

    @override
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan speed; this leaves Fast or WindFree, as on the remote."""
        await self._async_apply(fan=_HA_TO_FAN[fan_mode], special=Special.NONE)

    @override
    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the vertical swing."""
        horizontal = _SWING_FLAGS[self._ac.swing][1]
        await self._async_apply(
            swing=_FLAGS_TO_SWING[(swing_mode == SWING_ON, horizontal)]
        )

    @override
    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Set the horizontal swing."""
        vertical = _SWING_FLAGS[self._ac.swing][0]
        await self._async_apply(
            swing=_FLAGS_TO_SWING[(vertical, swing_horizontal_mode == SWING_ON)]
        )

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set Fast, WindFree or none."""
        await self._async_apply(special=_HA_TO_SPECIAL[preset_mode])


class SamsungIrClimateWithReceiver(SamsungIrClimate, InfraredReceiverConsumerEntity):
    """Samsung AC climate entity that also follows the physical remote."""

    def __init__(
        self, entry: ConfigEntry, emitter_entity_id: str, receiver_entity_id: str
    ) -> None:
        """Initialize the climate entity with a receiver."""
        super().__init__(entry, emitter_entity_id)
        self._infrared_receiver_entity_id = receiver_entity_id

    @override
    @callback
    def _handle_signal(self, signal: InfraredReceivedSignal) -> None:
        """Update the state from a frame sent by the physical remote."""
        received = decode_timings(signal.timings)
        if received is None:
            return
        _LOGGER.debug("Received Samsung AC frame: %s", received)

        if not received.power:
            # The power-off frame does not reliably describe the rest of the
            # state, so only the power changes.
            new_state = replace(self._ac, power=False)
        elif received.mode is Mode.AUTO or received.special is not Special.NONE:
            # The fan in the frame is forced; keep the speed chosen before.
            new_state = replace(received, fan=self._ac.fan)
        else:
            new_state = received

        if new_state != self._ac:
            self._ac = new_state
            self.async_write_ha_state()
