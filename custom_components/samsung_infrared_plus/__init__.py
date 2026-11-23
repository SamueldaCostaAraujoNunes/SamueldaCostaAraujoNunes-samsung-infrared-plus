"""Samsung Infrared Plus: Samsung TV and AC over infrared, with receiver support.

Based on the Home Assistant core ``samsung_infrared`` integration.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

PLATFORMS = [Platform.BUTTON, Platform.CLIMATE, Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Samsung Infrared Plus from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Samsung Infrared Plus config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
