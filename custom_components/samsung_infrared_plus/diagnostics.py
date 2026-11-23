"""Diagnostics support for Samsung Infrared Plus."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_TYPE,
    CONF_INFRARED_EMITTER_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    emitter_entity_id = entry.data[CONF_INFRARED_EMITTER_ENTITY_ID]
    receiver_entity_id = entry.data.get(CONF_INFRARED_RECEIVER_ENTITY_ID)
    emitter_state = hass.states.get(emitter_entity_id)
    receiver_state = hass.states.get(receiver_entity_id) if receiver_entity_id else None

    return {
        "device_type": entry.data[CONF_DEVICE_TYPE],
        "infrared_emitter_entity_id": emitter_entity_id,
        "infrared_emitter_state": emitter_state.state if emitter_state else None,
        "infrared_receiver_entity_id": receiver_entity_id,
        "infrared_receiver_state": receiver_state.state if receiver_state else None,
    }
