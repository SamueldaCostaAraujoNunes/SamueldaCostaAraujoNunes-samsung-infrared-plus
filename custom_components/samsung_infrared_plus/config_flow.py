"""Config flow for Samsung Infrared Plus."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.infrared import (
    DOMAIN as INFRARED_DOMAIN,
    async_get_emitters,
    async_get_receivers,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, translation
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_DEVICE_TYPE,
    CONF_INFRARED_EMITTER_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
    DOMAIN,
    UNIQUE_ID_PREFIX,
    SamsungDeviceType,
)


def _device_schema(hass: HomeAssistant, device_type: str) -> vol.Schema:
    """Return the emitter (and, for the AC, optional receiver) schema."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_INFRARED_EMITTER_ENTITY_ID): EntitySelector(
            EntitySelectorConfig(
                domain=INFRARED_DOMAIN, include_entities=async_get_emitters(hass)
            )
        )
    }
    if device_type == SamsungDeviceType.AC and (receivers := async_get_receivers(hass)):
        schema[vol.Optional(CONF_INFRARED_RECEIVER_ENTITY_ID)] = EntitySelector(
            EntitySelectorConfig(domain=INFRARED_DOMAIN, include_entities=receivers)
        )
    return vol.Schema(schema)


class SamsungIrPlusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Samsung Infrared Plus."""

    VERSION = 1

    _device_type: str

    async def _async_get_title(self, entity_id: str, device_type: str) -> str:
        """Build a title like "Samsung Air conditioner via IR Quarto"."""
        ent_reg = er.async_get(self.hass)
        entry = ent_reg.async_get(entity_id)
        entity_name = (
            entry.name or entry.original_name or entity_id if entry else entity_id
        )
        translations = await translation.async_get_translations(
            self.hass, self.hass.config.language, "selector", {DOMAIN}
        )
        device_type_name = translations.get(
            f"component.{DOMAIN}.selector.device_type.options.{device_type}",
            device_type,
        )
        return f"Samsung {device_type_name} via {entity_name}"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the device type."""
        if not async_get_emitters(self.hass):
            return self.async_abort(reason="no_emitters")

        if user_input is not None:
            self._device_type = user_input[CONF_DEVICE_TYPE]
            if self._device_type == SamsungDeviceType.AC:
                return await self.async_step_ac()
            return await self.async_step_tv()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_TYPE): SelectSelector(
                        SelectSelectorConfig(
                            options=[device_type.value for device_type in SamsungDeviceType],
                            translation_key=CONF_DEVICE_TYPE,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_tv(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the emitter for a TV."""
        return await self._async_step_device("tv", user_input)

    async def async_step_ac(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the emitter and the optional receiver for an air conditioner."""
        return await self._async_step_device("ac", user_input)

    async def _async_step_device(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if user_input is not None:
            emitter = user_input[CONF_INFRARED_EMITTER_ENTITY_ID]
            await self.async_set_unique_id(
                f"{UNIQUE_ID_PREFIX}{self._device_type}_{emitter}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=await self._async_get_title(emitter, self._device_type),
                data={CONF_DEVICE_TYPE: self._device_type, **user_input},
            )

        return self.async_show_form(
            step_id=step_id, data_schema=_device_schema(self.hass, self._device_type)
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the emitter or the receiver."""
        if not async_get_emitters(self.hass):
            return self.async_abort(reason="no_emitters")

        entry = self._get_reconfigure_entry()
        device_type = entry.data[CONF_DEVICE_TYPE]

        if user_input is not None:
            emitter = user_input[CONF_INFRARED_EMITTER_ENTITY_ID]
            await self.async_set_unique_id(f"{UNIQUE_ID_PREFIX}{device_type}_{emitter}")
            if self.unique_id != entry.unique_id:
                self._abort_if_unique_id_configured()
            # Replace rather than update the data, so a cleared receiver goes away.
            return self.async_update_reload_and_abort(
                entry,
                unique_id=self.unique_id,
                title=await self._async_get_title(emitter, device_type),
                data={CONF_DEVICE_TYPE: device_type, **user_input},
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _device_schema(self.hass, device_type), entry.data
            ),
        )
